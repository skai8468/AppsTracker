"""Shared scraper contract: the ``JobDTO`` every source produces, plus keyword-based
classification into sector / job-type / seniority.

Each source (MyCareersFuture, a company career page, manual entry) maps its raw payload
into ``JobDTO``. ``runner.py`` then upserts those into the ``Job`` table. Keeping the
classification here means every source is labelled consistently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..models import JobType, Sector

# --- keyword tables for classification -------------------------------------------------

_TECH_KEYWORDS = (
    "software", "engineer", "developer", "data", "machine learning", "ml ", "ai ",
    "backend", "frontend", "full stack", "fullstack", "devops", "cloud", "cyber",
    "security", "qa ", "sre", "platform", "infrastructure", "mobile", "ios", "android",
    "product manager", "technology", "it ", "information technology", "analytics",
)
_FINANCE_KEYWORDS = (
    "bank", "finance", "financial", "investment", "trading", "trader", "quant",
    "risk", "audit", "actuar", "wealth", "asset management", "equity", "credit",
    "treasury", "compliance", "accounting", "insurance", "capital markets", "fund",
)
_INTERN_KEYWORDS = ("intern", "internship", "attachment", "trainee")
_MA_KEYWORDS = (
    "management associate", "graduate programme", "graduate program",
    "management trainee", "associate programme", "associate program",
    "graduate associate", "rotational program", "leadership program",
    "graduate development", "management associate programme",
)
_GRAD_KEYWORDS = ("graduate", "entry level", "entry-level", "junior", "fresh grad")


@dataclass
class JobDTO:
    source: str
    source_job_id: str
    title: str
    company_name: str
    apply_url: str

    sector: Optional[Sector] = None
    category: Optional[str] = None
    job_type: Optional[JobType] = None
    seniority: Optional[str] = None

    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "SGD"
    salary_period: str = "month"

    location: Optional[str] = None
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    closing_at: Optional[datetime] = None

    # Extra hints a source may pass to help classification (category names, etc.).
    hints: list[str] = field(default_factory=list)

    def classify(self) -> None:
        """Fill sector / job_type when the source didn't set them, using keywords.

        Sector uses the full text (broad signal), but job_type is judged from the
        *title + category + hints* only — job descriptions routinely mention "graduate
        programme" or "junior" in boilerplate, which would mislabel senior roles.
        """
        sector_text = " ".join(
            [self.title, self.category or "", self.description or "", *self.hints]
        ).lower()
        type_text = " ".join(
            [self.title, self.category or "", self.seniority or "", *self.hints]
        ).lower()

        if self.sector is None:
            self.sector = _guess_sector(sector_text)
        if self.job_type is None:
            self.job_type = _guess_job_type(type_text)


def _guess_sector(text: str) -> Sector:
    if any(k in text for k in _FINANCE_KEYWORDS):
        # finance keywords are more specific; check them first
        finance_hits = sum(k in text for k in _FINANCE_KEYWORDS)
        tech_hits = sum(k in text for k in _TECH_KEYWORDS)
        return Sector.finance if finance_hits >= tech_hits else Sector.tech
    if any(k in text for k in _TECH_KEYWORDS):
        return Sector.tech
    return Sector.other


def _guess_job_type(text: str) -> JobType:
    if any(k in text for k in _MA_KEYWORDS):
        return JobType.ma_program
    if any(k in text for k in _INTERN_KEYWORDS):
        return JobType.internship
    if any(k in text for k in _GRAD_KEYWORDS):
        return JobType.grad
    return JobType.other


_SENIOR_MARKERS = (
    "senior", "snr", "sr.", "lead ", "head of", "director", "vp ", "vice president",
    "principal", "staff ", "manager", "expert", "specialist", "chief",
)


def keeps_for_freshgrad(dto: JobDTO) -> bool:
    """True if a job is relevant to a fresh grad / intern.

    Internships and MA/graduate programmes are always kept. Otherwise the *title* must
    not carry a senior marker — this is authoritative even for keyword-guessed "grad"
    roles, so a "Senior Software Engineer" whose description mentions "graduate" is
    still dropped.
    """
    if dto.job_type in (JobType.internship, JobType.ma_program):
        return True
    title = f"{dto.title} {dto.seniority or ''}".lower()
    return not any(m in title for m in _SENIOR_MARKERS)
