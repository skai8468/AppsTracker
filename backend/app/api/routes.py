"""REST endpoints: jobs board, application pipeline, email-event inbox, companies, admin.

Kept thin — DB access via SQLModel sessions, business rules (stage changes, matching)
live in the models / integration modules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models import (
    Application,
    AppStatus,
    Company,
    EmailEvent,
    Job,
    JobType,
    Sector,
    utcnow,
)
from ..scrapers.runner import _slugify
from .schemas import (
    ApplicationOut,
    ApplicationUpdateIn,
    ClassifyEmailIn,
    CompanyIn,
    CompanyOut,
    EmailEventOut,
    JobOut,
    TrackJobIn,
)

router = APIRouter()


# --- helpers --------------------------------------------------------------------------

def _job_to_out(job: Job, app: Optional[Application]) -> JobOut:
    return JobOut(
        id=job.id,
        source=job.source,
        title=job.title,
        company_name=job.company_name,
        sector=job.sector,
        category=job.category,
        job_type=job.job_type,
        seniority=job.seniority,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        location=job.location,
        apply_url=job.apply_url,
        posted_at=job.posted_at,
        closing_at=job.closing_at,
        is_active=job.is_active,
        application_id=app.id if app else None,
        application_status=app.status if app else None,
    )


# --- jobs -----------------------------------------------------------------------------

@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    session: Session = Depends(get_session),
    sector: Optional[Sector] = None,
    job_type: Optional[JobType] = None,
    q: Optional[str] = None,
    min_salary: Optional[float] = None,
    active_only: bool = True,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    stmt = select(Job)
    if active_only:
        stmt = stmt.where(Job.is_active == True)  # noqa: E712
    if sector:
        stmt = stmt.where(Job.sector == sector)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)
    if min_salary is not None:
        stmt = stmt.where(Job.salary_max >= min_salary)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (Job.title.ilike(like)) | (Job.company_name.ilike(like))
        )
    stmt = stmt.order_by(Job.posted_at.desc().nullslast(), Job.scraped_at.desc())
    jobs = session.exec(stmt.offset(offset).limit(limit)).all()

    # Attach tracking status in one lookup.
    app_by_job = {
        a.job_id: a
        for a in session.exec(
            select(Application).where(Application.job_id.in_([j.id for j in jobs]))
        ).all()
    } if jobs else {}
    return [_job_to_out(j, app_by_job.get(j.id)) for j in jobs]


# --- applications ---------------------------------------------------------------------

@router.post("/applications", response_model=ApplicationOut)
def track_job(body: TrackJobIn, session: Session = Depends(get_session)):
    job = session.get(Job, body.job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    existing = session.exec(
        select(Application).where(Application.job_id == body.job_id)
    ).first()
    if existing:
        raise HTTPException(409, "already tracking this job")

    app = Application(
        job_id=body.job_id,
        status=body.status,
        notes=body.notes,
        applied_at=utcnow() if body.status == AppStatus.applied else None,
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return _app_to_out(session, app)


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(session: Session = Depends(get_session)):
    apps = session.exec(
        select(Application).order_by(Application.last_stage_change_at.desc())
    ).all()
    return [_app_to_out(session, a) for a in apps]


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(
    app_id: int, body: ApplicationUpdateIn, session: Session = Depends(get_session)
):
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(404, "application not found")
    if body.status is not None and body.status != app.status:
        app.status = body.status
        app.last_stage_change_at = utcnow()
        if body.status == AppStatus.applied and app.applied_at is None:
            app.applied_at = utcnow()
    if body.notes is not None:
        app.notes = body.notes
    session.add(app)
    session.commit()
    session.refresh(app)
    return _app_to_out(session, app)


def _app_to_out(session: Session, app: Application) -> ApplicationOut:
    job = session.get(Job, app.job_id)
    return ApplicationOut(
        id=app.id,
        job_id=app.job_id,
        status=app.status,
        applied_at=app.applied_at,
        last_stage_change_at=app.last_stage_change_at,
        notes=app.notes,
        job=_job_to_out(job, app) if job else None,
    )


# --- email events (the "you classify" inbox) ------------------------------------------

@router.get("/email-events", response_model=list[EmailEventOut])
def list_email_events(
    session: Session = Depends(get_session), unread_only: bool = False
):
    stmt = select(EmailEvent).order_by(EmailEvent.received_at.desc().nullslast())
    if unread_only:
        stmt = stmt.where(EmailEvent.is_read == False)  # noqa: E712
    return session.exec(stmt).all()


@router.post("/email-events/{event_id}/classify", response_model=EmailEventOut)
def classify_email(
    event_id: int, body: ClassifyEmailIn, session: Session = Depends(get_session)
):
    event = session.get(EmailEvent, event_id)
    if event is None:
        raise HTTPException(404, "email event not found")
    event.classified_stage = body.stage
    event.is_read = True

    # Propagate the stage to the linked application, if any.
    if event.matched_application_id:
        app = session.get(Application, event.matched_application_id)
        if app and app.status != body.stage:
            app.status = body.stage
            app.last_stage_change_at = utcnow()
            session.add(app)

    session.add(event)
    session.commit()
    session.refresh(event)
    return event


# --- companies ------------------------------------------------------------------------

@router.get("/companies", response_model=list[CompanyOut])
def list_companies(session: Session = Depends(get_session)):
    return session.exec(select(Company).order_by(Company.name)).all()


@router.post("/companies", response_model=CompanyOut)
def create_company(body: CompanyIn, session: Session = Depends(get_session)):
    slug = _slugify(body.name)
    existing = session.exec(select(Company).where(Company.slug == slug)).first()
    if existing:
        raise HTTPException(409, "company already exists")
    company = Company(
        name=body.name,
        slug=slug,
        email_domains=body.email_domains,
        career_page_url=body.career_page_url,
        sector=body.sector,
        notes=body.notes,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int, body: CompanyIn, session: Session = Depends(get_session)
):
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    company.name = body.name
    company.email_domains = body.email_domains
    company.career_page_url = body.career_page_url
    company.sector = body.sector
    company.notes = body.notes
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


# --- admin / manual triggers ----------------------------------------------------------

@router.post("/admin/scrape")
def trigger_scrape():
    from ..scrapers.runner import run_scrape

    return run_scrape()


@router.post("/admin/poll-gmail")
def trigger_gmail_poll():
    from ..gmail.poller import poll_once

    return poll_once()
