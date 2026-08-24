"""Gmail poller: incremental fetch of new mail, match to tracked companies, act.

Flow per poll:
  * Read the stored ``gmail_history_id``. First run just records the current id (no backfill).
  * Use the History API to list message ids added since then.
  * For each new message, pull From / Subject / snippet / date.
  * ``process_message`` decides what to do (pure w.r.t. the DB session, so it's testable):
      - matches a company you APPLIED to + looks like a confirmation  -> flip app to
        ``confirmed`` and queue a "confirmation" notification.
      - matches any tracked company                                   -> store an
        EmailEvent and queue a "company_email" notification for you to classify.
  * Queued notifications are pushed to Telegram (best-effort).

``GMAIL_DRY_RUN=true`` logs matches without changing state or sending notifications.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from ..config import settings
from ..db import get_setting, session_scope, set_setting
from ..models import (
    Application,
    AppStatus,
    Company,
    EmailEvent,
    Job,
    Notification,
    utcnow,
)
from . import matchers
from .oauth import get_service

log = logging.getLogger(__name__)

HISTORY_KEY = "gmail_history_id"


# --- parsed message shape (decoupled from the Gmail API payload) -----------------------

class ParsedMessage:
    def __init__(
        self,
        message_id: str,
        thread_id: str,
        from_addr: str,
        subject: str,
        snippet: str,
        received_at: Optional[datetime],
    ):
        self.message_id = message_id
        self.thread_id = thread_id
        self.from_addr = from_addr
        self.subject = subject
        self.snippet = snippet
        self.received_at = received_at


def _header(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_api_message(msg: dict[str, Any]) -> ParsedMessage:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    internal = msg.get("internalDate")
    received = (
        datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)
        if internal
        else None
    )
    return ParsedMessage(
        message_id=msg.get("id", ""),
        thread_id=msg.get("threadId", ""),
        from_addr=_header(headers, "From"),
        subject=_header(headers, "Subject"),
        snippet=msg.get("snippet", ""),
        received_at=received,
    )


# --- core decision logic (testable: takes a session + parsed message) ------------------

def process_message(session: Session, msg: ParsedMessage) -> Optional[Notification]:
    """Match one message to a company and act. Returns a Notification to send, or None."""
    if session.exec(
        select(EmailEvent).where(EmailEvent.gmail_message_id == msg.message_id)
    ).first():
        return None  # already processed

    domain = matchers.extract_domain(msg.from_addr)
    if not domain:
        return None

    company = _match_company(session, domain)
    if company is None:
        return None

    # Is there an application to a job at this company?
    app = _application_for_company(session, company)

    is_confirmation = matchers.looks_like_confirmation(msg.subject, msg.snippet)

    event = EmailEvent(
        gmail_message_id=msg.message_id,
        thread_id=msg.thread_id,
        from_addr=msg.from_addr,
        subject=msg.subject,
        snippet=msg.snippet,
        received_at=msg.received_at,
        matched_company_id=company.id,
        matched_application_id=app.id if app else None,
    )

    if app and is_confirmation and app.status in (AppStatus.applied, AppStatus.interested):
        app.status = AppStatus.confirmed
        app.last_stage_change_at = utcnow()
        event.classified_stage = AppStatus.confirmed
        event.is_read = True
        session.add(app)
        session.add(event)
        session.commit()
        note = Notification(
            type="confirmation",
            payload=f"✅ Application confirmed at {company.name}\n{msg.subject}",
            ref_email_event_id=event.id,
        )
    else:
        session.add(event)
        session.commit()
        note = Notification(
            type="company_email",
            payload=f"📩 Email from {company.name}\n{msg.subject}",
            ref_email_event_id=event.id,
        )

    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _match_company(session: Session, domain: str) -> Optional[Company]:
    for company in session.exec(select(Company)).all():
        if matchers.domain_matches(domain, company.domain_list()):
            return company
    return None


def _application_for_company(session: Session, company: Company) -> Optional[Application]:
    stmt = (
        select(Application)
        .join(Job, Job.id == Application.job_id)
        .where(Job.company_id == company.id)
        .order_by(Application.last_stage_change_at.desc())
    )
    return session.exec(stmt).first()


# --- Gmail API plumbing ---------------------------------------------------------------

def _list_new_message_ids(service, start_history_id: str) -> tuple[list[str], Optional[str]]:
    ids: list[str] = []
    latest_history = start_history_id
    page_token = None
    while True:
        resp = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            )
            .execute()
        )
        for h in resp.get("history", []):
            latest_history = str(h.get("id", latest_history))
            for added in h.get("messagesAdded", []):
                mid = added.get("message", {}).get("id")
                if mid:
                    ids.append(mid)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids, resp.get("historyId", latest_history)


def poll_once() -> dict[str, Any]:
    """Run a single poll. Safe to call from the scheduler or the admin endpoint."""
    service = get_service()
    if service is None:
        return {"status": "gmail_not_configured"}

    with session_scope() as session:
        history_id = get_setting(session, HISTORY_KEY)

        if history_id is None:
            # First run: record the current mailbox state, don't backfill.
            profile = service.users().getProfile(userId="me").execute()
            set_setting(session, HISTORY_KEY, str(profile.get("historyId")))
            return {"status": "initialized", "history_id": profile.get("historyId")}

        try:
            message_ids, new_history = _list_new_message_ids(service, history_id)
        except Exception as exc:  # noqa: BLE001 - e.g. history id too old (404)
            log.warning("history.list failed (%s); reinitializing", exc)
            profile = service.users().getProfile(userId="me").execute()
            set_setting(session, HISTORY_KEY, str(profile.get("historyId")))
            return {"status": "reinitialized"}

        notifications: list[Notification] = []
        for mid in message_ids:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            parsed = _parse_api_message(msg)
            if settings.gmail_dry_run:
                log.info("[dry-run] %s | %s", parsed.from_addr, parsed.subject)
                continue
            note = process_message(session, parsed)
            if note:
                notifications.append(note)

        if not settings.gmail_dry_run:
            set_setting(session, HISTORY_KEY, str(new_history))

    # Send notifications outside the session scope.
    delivered = _deliver(notifications)
    return {
        "status": "ok",
        "new_messages": len(message_ids),
        "notifications": len(notifications),
        "delivered": delivered,
        "dry_run": settings.gmail_dry_run,
    }


def _deliver(notifications: list[Notification]) -> int:
    if not notifications:
        return 0
    from ..telegram.notify import send_notification

    delivered = 0
    with session_scope() as session:
        for note in notifications:
            if send_notification(note.payload):
                db_note = session.get(Notification, note.id)
                if db_note:
                    db_note.telegram_delivered = True
                    session.add(db_note)
                delivered += 1
        session.commit()
    return delivered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from ..db import init_db

    init_db()
    print(poll_once())
