"""poll_once resilience against a message that vanishes mid-poll.

Regression: Gmail's history feed can name a message that no longer exists (deleted, or
moved out of the mailbox). The per-message fetch then 404s, and because that aborted the
whole poll *before* the history id advanced, every later poll retried the same dead id —
the poller wedged permanently and stopped seeing new mail entirely.
"""
from __future__ import annotations

import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

from app.gmail import poller


class _FakeResp:
    def __init__(self, status):
        self.status = status


class _HttpError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.resp = _FakeResp(status)


class _Req:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error

    def execute(self):
        if self._error:
            raise self._error
        return self._result


class _Messages:
    def __init__(self, table):
        self.table = table
        self.fetched: list[str] = []

    def get(self, userId, id, format=None, metadataHeaders=None):
        self.fetched.append(id)
        entry = self.table[id]
        if isinstance(entry, Exception):
            return _Req(error=entry)
        return _Req(result=entry)


class _Users:
    def __init__(self, table, history):
        self._messages = _Messages(table)
        self._history = history

    def messages(self):
        return self._messages

    def history(self):
        outer = self

        class _H:
            def list(self, **kw):
                return _Req(result=outer._history)

        return _H()

    def getProfile(self, userId):
        return _Req(result={"historyId": "999"})


class _Service:
    def __init__(self, table, history):
        self._users = _Users(table, history)

    def users(self):
        return self._users


def _message(mid, from_addr, subject):
    return {
        "id": mid,
        "threadId": f"t-{mid}",
        "snippet": "",
        "internalDate": "1756000000000",
        "payload": {"headers": [
            {"name": "From", "value": from_addr},
            {"name": "Subject", "value": subject},
        ]},
    }


@pytest.fixture()
def wired(monkeypatch):
    """poll_once talks to module-level singletons; point them all at one temp DB."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    from contextlib import contextmanager

    @contextmanager
    def _scope():
        with Session(engine) as s:
            yield s

    store: dict[str, str] = {"gmail_history_id": "100"}
    monkeypatch.setattr(poller, "session_scope", _scope)
    monkeypatch.setattr(poller, "get_setting", lambda s, k: store.get(k))
    monkeypatch.setattr(poller, "set_setting",
                        lambda s, k, v: store.__setitem__(k, v))
    monkeypatch.setattr(poller, "_deliver", lambda notes: 0)
    return store


def test_vanished_message_is_skipped_and_history_still_advances(wired, monkeypatch):
    history = {
        "history": [{"id": "101", "messagesAdded": [
            {"message": {"id": "gone"}}, {"message": {"id": "live"}},
        ]}],
        "historyId": "202",
    }
    table = {
        "gone": _HttpError(404),
        "live": _message("live", "Careers <no-reply@unknown-co.com>", "Hello"),
    }
    service = _Service(table, history)
    monkeypatch.setattr(poller, "get_service", lambda: service)

    result = poller.poll_once()

    assert result["status"] == "ok"
    assert result["skipped"] == 1
    # The live message after the dead one still got fetched...
    assert service.users().messages().fetched == ["gone", "live"]
    # ...and crucially the history id moved on, so the next poll won't retry the dead id.
    assert wired["gmail_history_id"] == "202"


def test_notification_survives_the_history_commit(wired, monkeypatch):
    """Regression: a poll that produced a notification used to crash on delivery.

    set_setting commits at the end of poll_once, and a commit expires every instance in
    the session; _deliver then read note.payload after the session had closed and raised
    DetachedInstanceError. It never fired because every poll so far produced 0
    notifications — the first real confirmation would have hit it.
    """
    from app.gmail import poller as p
    from app.models import Company, Job, Application, AppStatus

    # Deliver for real (only the Telegram call is stubbed) so the detach path is exercised.
    monkeypatch.undo()
    sent: list[str] = []

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    from contextlib import contextmanager

    @contextmanager
    def _scope():
        with Session(engine) as s:
            yield s

    store = {"gmail_history_id": "100"}

    def _set_setting(session, key, value):
        # The real set_setting commits, and that commit is what expires the Notification
        # instances. A stub that skips it hides the very bug this test exists for.
        store[key] = value
        session.commit()

    monkeypatch.setattr(p, "session_scope", _scope)
    monkeypatch.setattr(p, "get_setting", lambda s, k: store.get(k))
    monkeypatch.setattr(p, "set_setting", _set_setting)
    monkeypatch.setattr("app.telegram.notify.send_notification",
                        lambda payload, chat_id=None: sent.append(payload) or True)

    with Session(engine) as s:
        c = Company(name="Acme", slug="acme", email_domains="acme.com")
        s.add(c); s.commit(); s.refresh(c)
        j = Job(source="manual", source_job_id="j1", title="Grad SWE",
                company_name="Acme", company_id=c.id, apply_url="http://x")
        s.add(j); s.commit(); s.refresh(j)
        s.add(Application(job_id=j.id, status=AppStatus.applied)); s.commit()

    history = {"history": [{"id": "101", "messagesAdded": [{"message": {"id": "conf"}}]}],
               "historyId": "202"}
    table = {"conf": _message("conf", "Careers <no-reply@acme.com>",
                              "Thank you for applying to Grad SWE")}
    monkeypatch.setattr(p, "get_service", lambda: _Service(table, history))

    result = p.poll_once()          # must not raise

    assert result["status"] == "ok"
    assert result["notifications"] == 1
    assert result["delivered"] == 1
    assert sent and "Acme" in sent[0]
    assert store["gmail_history_id"] == "202"


def test_transient_error_does_not_advance_history(wired, monkeypatch):
    """A 500 means try again later — advancing would silently lose that message."""
    history = {
        "history": [{"id": "101", "messagesAdded": [{"message": {"id": "flaky"}}]}],
        "historyId": "202",
    }
    service = _Service({"flaky": _HttpError(500)}, history)
    monkeypatch.setattr(poller, "get_service", lambda: service)

    with pytest.raises(Exception):
        poller.poll_once()
    assert wired["gmail_history_id"] == "100"      # unchanged, will retry
