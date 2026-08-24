"""Reusable fetcher for companies hosting jobs on Greenhouse.

Greenhouse exposes a clean public JSON board API:
    GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true

Lots of tech firms use it, so a single helper covers many employers — a company module
just calls ``fetch_greenhouse("<board-token>", company_name=...)``. Salary is usually
absent (Greenhouse doesn't expose it), so those JobDTOs leave salary empty.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx

from ...models import Sector
from ..base import JobDTO

log = logging.getLogger(__name__)

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").replace("&nbsp;", " ").strip()


def _is_singapore(location: str) -> bool:
    loc = (location or "").lower()
    return "singapore" in loc or loc.endswith(", sg") or " sg" in loc


async def fetch_greenhouse(
    token: str,
    company_name: str,
    sector: Sector | None = None,
    singapore_only: bool = True,
) -> list[JobDTO]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.get(
                BOARD_URL.format(token=token), params={"content": "true"}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Greenhouse fetch failed for %s: %s", company_name, exc)
            return []
        payload = resp.json()

    dtos: list[JobDTO] = []
    for job in payload.get("jobs", []) or []:
        location = ((job.get("location") or {}).get("name")) or ""
        if singapore_only and not _is_singapore(location):
            continue
        job_id = str(job.get("id") or "")
        if not job_id:
            continue
        posted = job.get("updated_at") or job.get("first_published")
        dto = JobDTO(
            source=f"company:{token}",
            source_job_id=job_id,
            title=(job.get("title") or "").strip(),
            company_name=company_name,
            apply_url=job.get("absolute_url") or "",
            sector=sector,
            location=location or "Singapore",
            description=_strip_html(job.get("content", ""))[:4000] or None,
            posted_at=_parse_iso(posted),
        )
        dto.classify()
        dtos.append(dto)
    return dtos


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
