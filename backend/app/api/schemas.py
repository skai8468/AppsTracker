"""Pydantic request/response schemas for the REST API (kept separate from DB models)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ..models import AppStatus, JobType, Sector


class JobOut(BaseModel):
    id: int
    source: str
    title: str
    company_name: str
    sector: Sector
    category: Optional[str]
    job_type: JobType
    seniority: Optional[str]
    salary_min: Optional[float]
    salary_max: Optional[float]
    salary_currency: str
    salary_period: str
    location: Optional[str]
    apply_url: str
    posted_at: Optional[datetime]
    closing_at: Optional[datetime]
    is_active: bool
    # Joined-in tracking status, if the user is already tracking this job.
    application_id: Optional[int] = None
    application_status: Optional[AppStatus] = None
    # Joined-in company info so the detail view can show and edit the tracked sender
    # domain(s) without a second /companies fetch and a client-side slug join.
    company_id: Optional[int] = None
    company_email_domains: str = ""


class CreateApplicationIn(BaseModel):
    """Add an application from a pasted job link. Title/company are usually auto-filled by
    the link-preview endpoint but the user can edit them before saving."""
    url: str
    title: str
    company: str
    # Comma-separated sender domain(s), e.g. "stripe.com". Powers Gmail confirmation
    # matching for this company; optional, can also be set later in Settings.
    email_domains: Optional[str] = None
    sector: Sector = Sector.other
    status: AppStatus = AppStatus.interested  # "Saved" by default; flip to applied later
    notes: Optional[str] = None


class LinkPreviewIn(BaseModel):
    url: str


class LinkPreviewOut(BaseModel):
    title: str
    company: str
    sector: Sector
    ok: bool


class ApplicationUpdateIn(BaseModel):
    """Partial update. Every field is optional; ``None`` means "leave unchanged".

    Beyond the application's own columns this also accepts the handful of joined Job /
    Company fields the detail view lets you edit, so the UI can save everything in one
    request instead of juggling three endpoints.
    """
    status: Optional[AppStatus] = None
    notes: Optional[str] = None
    # Lets the user correct the applied date (e.g. backdating a job applied for last week).
    applied_at: Optional[datetime] = None

    # --- joined Job fields ---
    title: Optional[str] = None
    company: Optional[str] = None
    apply_url: Optional[str] = None
    sector: Optional[Sector] = None
    # --- joined Company field: comma-separated sender domains for Gmail matching ---
    email_domains: Optional[str] = None


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    status: AppStatus
    applied_at: Optional[datetime]
    last_stage_change_at: datetime
    notes: Optional[str]
    job: Optional[JobOut] = None


class EmailEventOut(BaseModel):
    id: int
    from_addr: str
    subject: str
    snippet: str
    received_at: Optional[datetime]
    matched_company_id: Optional[int]
    matched_application_id: Optional[int]
    classified_stage: Optional[AppStatus]
    is_read: bool


class ClassifyEmailIn(BaseModel):
    stage: AppStatus


class CompanyIn(BaseModel):
    name: str
    email_domains: str = ""
    career_page_url: Optional[str] = None
    sector: Sector = Sector.other
    notes: Optional[str] = None


class CompanyPatchIn(BaseModel):
    """True partial update — unlike ``CompanyIn``, omitting a field leaves it alone.

    ``CompanyIn`` defaults its optional fields, so reusing it for PATCH silently wiped
    ``notes``/``career_page_url`` and reset ``sector`` whenever the UI sent just a name and
    a domain.
    """
    name: Optional[str] = None
    email_domains: Optional[str] = None
    career_page_url: Optional[str] = None
    sector: Optional[Sector] = None
    notes: Optional[str] = None


class GmailStatusOut(BaseModel):
    connected: bool


class CompanyOut(BaseModel):
    id: int
    name: str
    slug: str
    email_domains: str
    career_page_url: Optional[str]
    sector: Sector
    notes: Optional[str]
