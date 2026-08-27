"""process_message decision-logic tests against an isolated in-memory DB."""
from __future__ import annotations

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app.gmail.poller import ParsedMessage, process_message
from app.models import Application, AppStatus, Company, Job, Sector, utcnow


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed(session, app_status=AppStatus.applied):
    company = Company(
        name="Acme Tech", slug="acme-tech", email_domains="acme.com", sector=Sector.tech
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(
        source="mcf", source_job_id="J1", title="Grad SWE",
        company_name="Acme Tech", company_id=company.id, apply_url="http://x",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    app = Application(job_id=job.id, status=app_status)
    session.add(app)
    session.commit()
    session.refresh(app)
    return company, job, app


def _msg(subject, from_addr="Careers <no-reply@acme.com>", mid="m1"):
    return ParsedMessage(mid, "t1", from_addr, subject, "", None)


def test_confirmation_flips_application(session):
    _company, _job, app = _seed(session)
    note = process_message(session, _msg("We have received your application"))
    session.refresh(app)
    assert app.status == AppStatus.confirmed
    assert note is not None and note.type == "confirmation"


def test_non_confirmation_creates_company_email(session):
    _company, _job, app = _seed(session)
    note = process_message(session, _msg("Interview invitation"))
    session.refresh(app)
    assert app.status == AppStatus.applied  # unchanged; user will classify
    assert note is not None and note.type == "company_email"


def test_unknown_sender_ignored(session):
    _seed(session)
    note = process_message(session, _msg("Anything", from_addr="hi@random.com"))
    assert note is None


def _add_job(session, company, title, app_status=AppStatus.applied, url="http://x"):
    job = Job(
        source="manual", source_job_id=title, title=title,
        company_name=company.name, company_id=company.id, apply_url=url,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    app = Application(job_id=job.id, status=app_status)
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


# --- several open roles at one employer ------------------------------------------------

def test_confirmation_picks_the_role_named_in_the_email(session):
    """Recency alone would flip the wrong role; the title in the subject decides."""
    company, _job, first = _seed(session)                      # "Grad SWE"
    second = _add_job(session, company, "Quantitative Risk Analyst")

    note = process_message(
        session,
        _msg("We have received your application for the Quantitative Risk Analyst role"),
    )
    session.refresh(first)
    session.refresh(second)
    assert second.status == AppStatus.confirmed
    assert first.status == AppStatus.applied          # untouched
    assert note is not None and note.type == "confirmation"


def test_requisition_id_in_the_email_wins(session):
    """ATS mail often names the role vaguely but always carries the posting id."""
    company, _job, first = _seed(session)
    second = _add_job(
        session, company, "Associate", url="https://higher.acme.com/roles/170769"
    )

    process_message(session, _msg("Thank you for applying (ref 170769)", mid="ref"))
    session.refresh(first)
    session.refresh(second)
    assert second.status == AppStatus.confirmed
    assert first.status == AppStatus.applied


def test_ambiguous_email_falls_back_to_most_recent(session):
    """Nothing distinguishes the roles, so don't guess — keep the old recency behaviour."""
    company, _job, first = _seed(session)
    second = _add_job(session, company, "Quantitative Risk Analyst")
    second.last_stage_change_at = utcnow()
    session.add(second)
    session.commit()

    process_message(session, _msg("Thank you for applying", mid="vague"))
    session.refresh(second)
    assert second.status == AppStatus.confirmed       # most recently touched


# --- creating applications straight from confirmation emails ---------------------------

def _apps(session):
    from sqlmodel import select as _select
    return session.exec(_select(Application)).all()


def test_confirmation_from_untracked_sender_creates_the_application(session):
    """The whole point: applying somewhere new shouldn't need typing it in afterwards."""
    note = process_message(session, _msg(
        "Thank you for applying to Data Analyst, Growth",
        from_addr="Monee Recruitment <talent@monee.com>",
    ))
    apps = _apps(session)
    assert len(apps) == 1
    assert apps[0].status == AppStatus.confirmed

    job = session.get(Job, apps[0].job_id)
    assert job.title == "Data Analyst, Growth"
    assert job.company_name == "Monee"
    assert job.source == "email"

    company = session.get(Company, job.company_id)
    assert company.email_domains == "monee.com"   # tracked from here on, no manual step
    assert note is not None and "New application tracked" in note.payload


def test_confirmation_without_a_named_role_still_records_it(session):
    """"Thank you for applying to Sea!" names no role — track it, don't drop it."""
    process_message(session, _msg(
        "Thank you for applying to Sea!", from_addr="Sea Careers <no-reply@sea.com>",
    ))
    apps = _apps(session)
    assert len(apps) == 1
    job = session.get(Job, apps[0].job_id)
    assert job.company_name == "Sea"
    assert job.title == "Role not specified"      # editable in the app


def test_second_role_at_a_tracked_company_is_added_not_conflated(session):
    """A confirmation for a role we don't track must not re-confirm a different one."""
    _company, _job, existing = _seed(session)     # Acme, "Grad SWE"
    process_message(session, _msg("Thank you for applying to Quantitative Risk Analyst"))

    session.refresh(existing)
    assert existing.status == AppStatus.applied   # untouched
    titles = sorted(session.get(Job, a.job_id).title for a in _apps(session))
    assert titles == ["Grad SWE", "Quantitative Risk Analyst"]


def test_confirmation_for_a_tracked_role_confirms_rather_than_duplicating(session):
    _company, _job, existing = _seed(session)     # "Grad SWE"
    process_message(session, _msg("Thank you for applying to Grad SWE"))
    session.refresh(existing)
    assert existing.status == AppStatus.confirmed
    assert len(_apps(session)) == 1               # no duplicate


def test_untracked_noise_never_creates_an_application(session):
    assert process_message(session, _msg(
        "Your verification code is 1234", from_addr="Portal <no-reply@random-portal.com>",
    )) is None
    assert _apps(session) == []


def test_auto_tracking_can_be_switched_off(session, monkeypatch):
    from app.gmail import poller as p
    monkeypatch.setattr(p.settings, "auto_track_from_email", False)
    assert process_message(session, _msg(
        "Thank you for applying to Data Analyst",
        from_addr="Monee <talent@monee.com>",
    )) is None
    assert _apps(session) == []


# --- transactional noise from a tracked domain -----------------------------------------

def test_login_code_from_tracked_domain_is_filed_not_notified(session):
    """Portal login codes share the company's domain but aren't about an application."""
    _company, _job, app = _seed(session)
    note = process_message(session, _msg("Your verification code is 483920"))
    session.refresh(app)
    assert note is None                       # no Telegram ping
    assert app.status == AppStatus.applied    # stage untouched


def test_noise_email_is_still_stored_so_it_can_be_recovered(session):
    from app.models import EmailEvent
    from sqlmodel import select

    _seed(session)
    process_message(session, _msg("Reset your password", mid="pw"))
    ev = session.exec(select(EmailEvent).where(EmailEvent.gmail_message_id == "pw")).first()
    assert ev is not None                     # kept, not dropped
    assert ev.is_read is True                 # filed under Unrelated
    assert ev.classified_stage is None


def test_confirmation_wins_over_noise_wording(session):
    """A real confirmation that also asks you to verify your email must still confirm."""
    _company, _job, app = _seed(session)
    note = process_message(
        session,
        _msg("Thank you for applying — please verify your email to continue"),
    )
    session.refresh(app)
    assert app.status == AppStatus.confirmed
    assert note is not None and note.type == "confirmation"


def test_job_alerts_do_not_reach_the_inbox_queue(session):
    _seed(session)
    assert process_message(session, _msg("New jobs matching your profile", mid="alert")) is None


def test_duplicate_message_ignored(session):
    _seed(session)
    first = process_message(session, _msg("Application received", mid="dup"))
    second = process_message(session, _msg("Application received", mid="dup"))
    assert first is not None
    assert second is None
