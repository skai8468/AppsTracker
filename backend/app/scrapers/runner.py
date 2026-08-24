"""Scrape orchestration: run the sources, upsert into the ``Job`` table, link companies.

Idempotent — jobs are keyed on ``(source, source_job_id)`` so re-scraping updates in place
rather than duplicating. Company-page fetchers are each wrapped in try/except so one broken
site never aborts the whole pass.

Run manually:  ``python -m app.scrapers.runner``
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from sqlmodel import Session, select

from ..db import session_scope
from ..models import Company, Job, Sector
from .base import JobDTO, keeps_for_freshgrad
from .companies import all_fetchers
from .mycareersfuture import fetch_freshgrad_jobs

log = logging.getLogger(__name__)


async def collect_all() -> list[JobDTO]:
    """Gather JobDTOs from every source. Company failures are isolated."""
    dtos: list[JobDTO] = []

    try:
        mcf = await fetch_freshgrad_jobs()
        log.info("MCF: %d jobs", len(mcf))
        dtos += mcf
    except Exception as exc:  # noqa: BLE001 - never let one source kill the pass
        log.exception("MCF source failed: %s", exc)

    for slug, fetch in all_fetchers().items():
        try:
            jobs = await fetch()
            log.info("company:%s -> %d jobs", slug, len(jobs))
            dtos += jobs
        except Exception as exc:  # noqa: BLE001
            log.exception("company:%s failed: %s", slug, exc)

    # Drop clearly-senior roles that slipped through.
    return [d for d in dtos if keeps_for_freshgrad(d)]


def _upsert(session: Session, dto: JobDTO) -> bool:
    """Insert or update one job. Returns True if newly created."""
    existing = session.exec(
        select(Job).where(
            Job.source == dto.source, Job.source_job_id == dto.source_job_id
        )
    ).first()

    company = _get_or_create_company(session, dto)

    fields = asdict(dto)
    fields.pop("hints", None)
    fields["company_id"] = company.id if company else None
    fields["is_active"] = True

    if existing is None:
        job = Job(**fields)
        session.add(job)
        return True

    for key, value in fields.items():
        if key == "scraped_at":
            continue
        setattr(existing, key, value)
    from ..models import utcnow

    existing.scraped_at = utcnow()
    session.add(existing)
    return False


def _get_or_create_company(session: Session, dto: JobDTO) -> Company | None:
    name = (dto.company_name or "").strip()
    if not name:
        return None
    slug = _slugify(name)
    company = session.exec(select(Company).where(Company.slug == slug)).first()
    if company is None:
        company = Company(
            name=name,
            slug=slug,
            sector=dto.sector or Sector.other,
        )
        session.add(company)
        session.commit()
        session.refresh(company)
    return company


def _slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:80]


def run_scrape() -> dict[str, int]:
    """Synchronous entry point used by the scheduler and the CLI."""
    dtos = asyncio.run(collect_all())
    created = 0
    with session_scope() as session:
        for dto in dtos:
            if _upsert(session, dto):
                created += 1
        session.commit()
    stats = {"collected": len(dtos), "created": created, "updated": len(dtos) - created}
    log.info("scrape done: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from ..db import init_db

    init_db()
    print(run_scrape())
