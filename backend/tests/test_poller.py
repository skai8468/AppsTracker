"""process_message decision-logic tests against an isolated in-memory DB."""
from __future__ import annotations

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app.gmail.poller import ParsedMessage, process_message
from app.models import Application, AppStatus, Company, Job, Sector


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


def test_duplicate_message_ignored(session):
    _seed(session)
    first = process_message(session, _msg("Application received", mid="dup"))
    second = process_message(session, _msg("Application received", mid="dup"))
    assert first is not None
    assert second is None
