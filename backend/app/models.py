"""Database models (SQLModel) and the enums that constrain their key fields.

Five tables back the whole app:

* ``Company``       — employers we track (drives the Gmail domain matcher).
* ``Job``           — normalized job listings from every source.
* ``Application``   — the user's own tracking record for a job.
* ``EmailEvent``    — relevant emails the Gmail poller caught, awaiting classification.
* ``Notification``  — audit trail of Telegram pushes so we never double-notify.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sector(str, Enum):
    tech = "tech"
    finance = "finance"
    other = "other"


class JobType(str, Enum):
    grad = "grad"            # fresh-grad / entry-level full-time
    internship = "internship"
    ma_program = "ma_program"  # management associate / graduate programme
    other = "other"


class AppStatus(str, Enum):
    interested = "interested"
    applied = "applied"
    confirmed = "confirmed"      # auto-flipped when a confirmation email arrives
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    career_page_url: Optional[str] = None
    # Comma-separated email domains (e.g. "dbs.com,dbs.com.sg") the Gmail matcher keys off.
    email_domains: str = ""
    sector: Sector = Sector.other
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    def domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.email_domains.split(",") if d.strip()]


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "source_job_id", name="uq_source_job"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)            # "mcf" | "company:<slug>" | "manual"
    source_job_id: str = Field(index=True)
    title: str
    company_name: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)

    sector: Sector = Field(default=Sector.other, index=True)
    category: Optional[str] = None
    job_type: JobType = Field(default=JobType.other, index=True)
    seniority: Optional[str] = None

    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "SGD"
    salary_period: str = "month"               # "month" | "year" | "hour"

    location: Optional[str] = None
    apply_url: str
    description: Optional[str] = None

    posted_at: Optional[datetime] = None
    closing_at: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=utcnow)
    is_active: bool = Field(default=True, index=True)


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="jobs.id", index=True, unique=True)
    status: AppStatus = Field(default=AppStatus.interested, index=True)
    applied_at: Optional[datetime] = None
    last_stage_change_at: datetime = Field(default_factory=utcnow)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class EmailEvent(SQLModel, table=True):
    __tablename__ = "email_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    gmail_message_id: str = Field(index=True, unique=True)
    thread_id: Optional[str] = None
    from_addr: str = ""
    subject: str = ""
    snippet: str = ""
    received_at: Optional[datetime] = None

    matched_company_id: Optional[int] = Field(default=None, foreign_key="companies.id")
    matched_application_id: Optional[int] = Field(
        default=None, foreign_key="applications.id", index=True
    )
    # Set once the user (or the confirmation auto-detect) classifies it.
    classified_stage: Optional[AppStatus] = None
    is_read: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(index=True)              # "confirmation" | "company_email" | "digest"
    payload: str = ""                          # human-readable message body
    ref_email_event_id: Optional[int] = Field(default=None, foreign_key="email_events.id")
    sent_at: datetime = Field(default_factory=utcnow)
    telegram_delivered: bool = Field(default=False)


class Setting(SQLModel, table=True):
    """Tiny key/value store for singletons like the Gmail historyId and Telegram chat_id."""

    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = ""
