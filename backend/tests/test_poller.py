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


def test_unclassifiable_mail_creates_company_email(session):
    """Anything the matchers can't read is queued for the user, stage untouched."""
    _company, _job, app = _seed(session)
    note = process_message(session, _msg("A quick update on your candidacy"))
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


# --- shared applicant-tracking platforms ------------------------------------------------

def test_ats_domain_is_not_claimed_as_the_employers_domain(session):
    """EY mails via yello.co. Saving that as EY's domain would hand the next Yello
    employer's mail straight to EY."""
    process_message(session, _msg(
        "Thanks for applying at EY",
        from_addr="EY Talent Attraction and Acquisition Team <eyglobal@yello.co>",
    ))
    from sqlmodel import select as _select
    company = session.exec(_select(Company)).all()[-1]
    assert company.name == "EY"              # display name cleaned down to the employer
    assert company.email_domains == ""       # the platform's domain is not EY's


def test_two_employers_on_one_platform_stay_separate(session):
    process_message(session, _msg(
        "Thanks for applying at EY", mid="ey",
        from_addr="EY Careers <noreply@yello.co>"))
    process_message(session, _msg(
        "Thank you for applying to Data Analyst", mid="acme",
        from_addr="Acme Talent Team <noreply@yello.co>"))

    from sqlmodel import select as _select
    names = sorted(c.name for c in session.exec(_select(Company)).all())
    assert names == ["Acme", "EY"]           # not both filed under EY
    assert len(session.exec(_select(Application)).all()) == 2


def test_repeat_mail_via_a_platform_finds_the_same_company(session):
    process_message(session, _msg(
        "Thanks for applying at EY", mid="one",
        from_addr="EY Talent Attraction and Acquisition Team <eyglobal@yello.co>"))
    process_message(session, _msg(
        "Thank you for applying to Audit Associate", mid="two",
        from_addr="EY <eyglobal@yello.co>"))

    from sqlmodel import select as _select
    assert [c.name for c in session.exec(_select(Company)).all()] == ["EY"]
    assert len(session.exec(_select(Application)).all()) == 2   # two roles, one company


def test_ats_domain_saved_against_a_company_is_ignored_when_matching(session):
    """Legacy data: an ATS domain stored before this rule must not match other employers."""
    stale = Company(name="Old Co", slug="old-co", email_domains="oracle.com")
    session.add(stale)
    session.commit()

    process_message(session, _msg(
        "Thank you for applying to Analyst",
        from_addr="Different Employer <noreply@oracle.com>"))

    from sqlmodel import select as _select
    names = sorted(c.name for c in session.exec(_select(Company)).all())
    assert "Different Employer" in names      # not filed under Old Co
    apps = session.exec(_select(Application)).all()
    assert len(apps) == 1
    job = session.get(Job, apps[0].job_id)
    assert job.company_name == "Different Employer"


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


# --- interview / assessment invitations -------------------------------------------------
#
# All of these are the JPMorgan HireVue invitation that went missing, and the ways it could
# have gone missing: the platform signs the mail, and when it signs the employer instead it
# spells the name differently from the job posting the application came from.

def _seed_named(session, name, slug, domain, status=AppStatus.applied, title="Grad SWE"):
    company = Company(name=name, slug=slug, email_domains=domain, sector=Sector.finance)
    session.add(company)
    session.commit()
    session.refresh(company)
    job = Job(
        source="manual", source_job_id=slug + "-1", title=title,
        company_name=name, company_id=company.id, apply_url="http://x",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    app = Application(job_id=job.id, status=status)
    session.add(app)
    session.commit()
    session.refresh(app)
    return company, app


def test_platform_spelling_of_the_employer_still_finds_the_company(session):
    """Tracked as "J.P. Morgan"; HireVue signs "JPMorganChase". Slug equality missed it."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    note = process_message(session, _msg(
        "Complete your video interview",
        from_addr="JPMorganChase Recruiting <no-reply@hirevue.com>",
        mid="hv1",
    ))
    session.refresh(app)
    assert app.status == AppStatus.interviewing
    assert note is not None and note.type == "interview"


def test_platform_signing_its_own_name_falls_back_to_the_subject(session):
    """"HireVue <no-reply@hirevue.com>" names nobody; the employer is in the subject."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    note = process_message(session, _msg(
        "Your J.P. Morgan video interview is ready",
        from_addr="HireVue <no-reply@hirevue.com>",
        mid="hv2",
    ))
    session.refresh(app)
    assert app.status == AppStatus.interviewing
    assert note is not None and note.type == "interview"


def test_the_platform_never_becomes_an_employer(session):
    """Filing this under a new company called "HireVue" is worse than not filing it."""
    note = process_message(session, _msg(
        "Complete your video interview",
        from_addr="HireVue <no-reply@hirevue.com>",
        mid="hv3",
    ))
    from sqlmodel import select as _select
    assert note is None
    assert session.exec(_select(Company)).all() == []
    assert _apps(session) == []


def test_the_vendors_domain_is_enough_without_invitation_wording(session):
    """Assessment vendors word their subjects freely; nothing else mails from there."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    process_message(session, _msg(
        "Action required by Friday",
        from_addr="JPMorganChase <noreply@hirevue.com>",
        mid="hv4",
    ))
    session.refresh(app)
    assert app.status == AppStatus.interviewing


def test_an_invitation_outranks_the_confirmation_wording_it_repeats(session):
    """These mails restate "thank you for applying"; the later stage has to win."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    process_message(session, _msg(
        "Thank you for applying — please complete your video interview",
        from_addr="Careers <campus@jpmorgan.com>",
        mid="hv5",
    ))
    session.refresh(app)
    assert app.status == AppStatus.interviewing


def test_a_rejection_that_mentions_the_interview_does_not_advance_the_stage(session):
    """"Following your video interview…" matches every invitation phrase there is."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    note = process_message(session, ParsedMessage(
        "hv6", "t1", "JPMorganChase <no-reply@hirevue.com>",
        "An update on your candidacy",
        "Unfortunately, following your video interview we will not be moving forward.",
        None,
    ))
    session.refresh(app)
    assert app.status == AppStatus.applied          # left for the user to classify
    assert note is not None and note.type == "company_email"


def test_a_vendors_login_code_is_not_an_interview(session):
    """The one thing an assessment vendor sends that is not about sitting one."""
    _company, app = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    note = process_message(session, _msg(
        "Your verification code is 481920",
        from_addr="JPMorganChase <no-reply@hirevue.com>",
        mid="hv7",
    ))
    session.refresh(app)
    assert note is None
    assert app.status == AppStatus.applied


def test_an_invitation_for_an_untracked_role_lands_at_the_interview_stage(session):
    """Filing it as "confirmed" would lose the fact that made it worth catching."""
    company, existing = _seed_named(session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com")
    process_message(session, _msg(
        "Your application for Quantitative Research Analyst — video interview invitation",
        from_addr="Careers <campus@jpmorgan.com>",
        mid="hv8",
    ))
    session.refresh(existing)
    assert existing.status == AppStatus.applied     # untouched
    new = [a for a in _apps(session) if a.id != existing.id]
    assert len(new) == 1 and new[0].status == AppStatus.interviewing


def test_an_offer_is_not_walked_back_by_a_late_reminder(session):
    """Stages past what the poller can infer are the user's; don't overwrite them."""
    _company, app = _seed_named(
        session, "J.P. Morgan", "j-p-morgan", "jpmorgan.com", status=AppStatus.offer
    )
    process_message(session, _msg(
        "Reminder: complete your video interview",
        from_addr="JPMorganChase <no-reply@hirevue.com>",
        mid="hv9",
    ))
    session.refresh(app)
    assert app.status == AppStatus.offer
