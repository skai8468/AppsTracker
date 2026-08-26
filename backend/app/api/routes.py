"""REST endpoints: link preview, application pipeline, email-event inbox, companies, admin.

Kept thin — DB access via SQLModel sessions, business rules (stage changes, matching)
live in the models / integration modules.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..linkpreview import fetch_meta
from ..models import (
    Application,
    AppStatus,
    Company,
    EmailEvent,
    Job,
    utcnow,
)
from ..util import slugify
from .schemas import (
    ApplicationOut,
    ApplicationUpdateIn,
    ClassifyEmailIn,
    CompanyIn,
    CompanyOut,
    CreateApplicationIn,
    EmailEventOut,
    JobOut,
    LinkPreviewIn,
    LinkPreviewOut,
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


# --- link preview ---------------------------------------------------------------------

@router.post("/applications/preview", response_model=LinkPreviewOut)
def preview_link(body: LinkPreviewIn):
    """Best-effort fetch of the pasted URL to pre-fill title/company. Never creates
    anything; ``ok=false`` means the user should type the fields in."""
    return LinkPreviewOut(**fetch_meta(body.url))


# --- applications ---------------------------------------------------------------------

@router.post("/applications", response_model=ApplicationOut)
def create_application(body: CreateApplicationIn, session: Session = Depends(get_session)):
    """Track a job from a pasted link: find-or-create its company, store a manual Job row,
    and open an Application (defaulting to the 'Saved' stage)."""
    url = body.url.strip()
    if not url:
        raise HTTPException(422, "url is required")

    # Don't track the same link twice.
    dupe = session.exec(
        select(Application).join(Job, Job.id == Application.job_id).where(Job.apply_url == url)
    ).first()
    if dupe:
        raise HTTPException(409, "already tracking this link")

    company = _get_or_create_company(session, body.company, body.sector, body.email_domains)
    job = Job(
        source="manual",
        source_job_id=uuid.uuid4().hex,
        title=body.title.strip() or url,
        company_name=body.company.strip(),
        company_id=company.id if company else None,
        sector=body.sector,
        apply_url=url,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    app = Application(
        job_id=job.id,
        status=body.status,
        notes=body.notes,
        applied_at=utcnow() if body.status == AppStatus.applied else None,
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return _app_to_out(session, app)


def _get_or_create_company(
    session: Session, name: str, sector, email_domains: Optional[str] = None
) -> Optional[Company]:
    name = (name or "").strip()
    if not name:
        return None
    domains = (email_domains or "").strip()
    slug = slugify(name)
    company = session.exec(select(Company).where(Company.slug == slug)).first()
    if company is None:
        company = Company(name=name, slug=slug, sector=sector, email_domains=domains)
        session.add(company)
        session.commit()
        session.refresh(company)
    elif domains and not company.email_domains:
        # Backfill: an earlier job at this company left domains unset — this add supplies
        # them, so Gmail matching starts working without a separate trip to Settings.
        company.email_domains = domains
        session.add(company)
        session.commit()
        session.refresh(company)
    return company


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


@router.delete("/applications/{app_id}", status_code=204)
def delete_application(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(404, "application not found")
    # Detach any email events pointing at this application so they aren't orphaned.
    for ev in session.exec(
        select(EmailEvent).where(EmailEvent.matched_application_id == app_id)
    ).all():
        ev.matched_application_id = None
        session.add(ev)
    job = session.get(Job, app.job_id)
    session.delete(app)
    if job is not None and job.source == "manual":
        session.delete(job)
    session.commit()


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
    slug = slugify(body.name)
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

@router.post("/admin/poll-gmail")
def trigger_gmail_poll():
    from ..gmail.poller import poll_once

    return poll_once()
