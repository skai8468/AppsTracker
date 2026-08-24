"""MyCareersFuture (MCF) search-API client.

MCF is Singapore's government job portal. Its search endpoint returns JSON that already
includes salary ranges, categories, employment types and position levels — which is why
it's our primary source. The API is **undocumented/unofficial**, so everything here is
defensive: deep ``.get`` chains, best-effort URL construction, and all network access
isolated in one place. Parsing (``parse_results``) is separated from fetching so tests can
feed recorded JSON with no live calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from ..models import JobType, Sector
from .base import JobDTO

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.mycareersfuture.gov.sg/v2/search"
JOB_URL_TEMPLATE = "https://www.mycareersfuture.gov.sg/job/{job_post_id}"

# Categories we care about (MCF uses these human-readable names).
TECH_CATEGORIES = ["Information Technology"]
FINANCE_CATEGORIES = ["Banking and Finance", "Accounting / Auditing / Taxation"]

# Fresh-grad / intern position levels.
JUNIOR_POSITION_LEVELS = ["Fresh/entry level", "Junior Executive", "Non-executive"]


def _salary_type_to_period(salary_type: str | None) -> str:
    st = (salary_type or "").lower()
    if "year" in st or "annual" in st:
        return "year"
    if "hour" in st:
        return "hour"
    return "month"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _sector_from_categories(categories: list[str]) -> Sector | None:
    joined = " ".join(categories).lower()
    if any(c.lower() in joined for c in (c.lower() for c in FINANCE_CATEGORIES)):
        return Sector.finance
    if "information technology" in joined:
        return Sector.tech
    return None


def parse_results(payload: dict[str, Any]) -> list[JobDTO]:
    """Turn a raw MCF search response into JobDTOs. No network access."""
    dtos: list[JobDTO] = []
    for item in payload.get("results", []) or []:
        uuid = item.get("uuid") or ""
        metadata = item.get("metadata") or {}
        job_post_id = metadata.get("jobPostId") or uuid
        if not job_post_id:
            continue

        salary = item.get("salary") or {}
        salary_type = ((salary.get("type") or {}).get("salaryType"))

        categories = [
            (c or {}).get("category", "")
            for c in (item.get("categories") or [])
        ]
        position_levels = [
            (p or {}).get("position", "")
            for p in (item.get("positionLevels") or [])
        ]
        employment_types = [
            (e or {}).get("employmentType", "")
            for e in (item.get("employmentTypes") or [])
        ]

        apply_url = metadata.get("jobDetailsUrl") or JOB_URL_TEMPLATE.format(
            job_post_id=job_post_id
        )

        dto = JobDTO(
            source="mcf",
            source_job_id=job_post_id,
            title=item.get("title", "").strip(),
            company_name=((item.get("postedCompany") or {}).get("name") or "").strip()
            or "Undisclosed company",
            apply_url=apply_url,
            category=", ".join(c for c in categories if c) or None,
            sector=_sector_from_categories(categories),
            job_type=_job_type_from_employment(employment_types, categories, position_levels),
            seniority=", ".join(p for p in position_levels if p) or None,
            salary_min=salary.get("minimum"),
            salary_max=salary.get("maximum"),
            salary_currency="SGD",
            salary_period=_salary_type_to_period(salary_type),
            location=_first_region(item.get("address")),
            description=(item.get("description") or "")[:4000] or None,
            posted_at=_parse_dt(
                metadata.get("newPostingDate") or metadata.get("originalPostingDate")
            ),
            closing_at=_parse_dt(metadata.get("expiryDate")),
            hints=employment_types + position_levels,
        )
        dto.classify()  # fill any gaps from keywords
        dtos.append(dto)
    return dtos


def _first_region(address: Any) -> str | None:
    if not isinstance(address, dict):
        return None
    districts = address.get("districts") or []
    if districts and isinstance(districts[0], dict):
        return districts[0].get("region")
    return None


def _job_type_from_employment(
    employment_types: list[str], categories: list[str], position_levels: list[str]
) -> JobType | None:
    joined = " ".join(employment_types + categories + position_levels).lower()
    if "intern" in joined or "attachment" in joined or "traineeship" in joined:
        return JobType.internship
    return None  # let keyword classifier decide grad vs ma_program vs other


def _search_body(
    categories: list[str], employment_types: list[str], position_levels: list[str]
) -> dict[str, Any]:
    body: dict[str, Any] = {"sessionId": "", "search": ""}
    if categories:
        body["categories"] = categories
    if employment_types:
        body["employmentTypes"] = employment_types
    if position_levels:
        body["positionLevels"] = position_levels
    return body


async def _fetch_pages(
    client: httpx.AsyncClient,
    categories: list[str],
    employment_types: list[str],
    position_levels: list[str],
    max_pages: int,
    limit: int,
) -> list[JobDTO]:
    out: list[JobDTO] = []
    body = _search_body(categories, employment_types, position_levels)
    for page in range(max_pages):
        try:
            resp = await client.post(
                SEARCH_URL,
                params={"limit": limit, "page": page},
                json=body,
                headers={"content-type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # network / rate-limit / schema hiccup
            log.warning("MCF fetch failed (page %s): %s", page, exc)
            break
        payload = resp.json()
        dtos = parse_results(payload)
        out.extend(dtos)
        if len(dtos) < limit:  # last page
            break
    return out


async def fetch_freshgrad_jobs(max_pages: int = 5, limit: int = 20) -> list[JobDTO]:
    """Fetch tech + finance fresh-grad / intern / grad-programme jobs from MCF.

    Runs several targeted searches (tech and finance, junior levels + internships) and
    dedupes by ``source_job_id``.
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        results: list[JobDTO] = []
        for cats in (TECH_CATEGORIES, FINANCE_CATEGORIES):
            results += await _fetch_pages(
                client, cats, [], JUNIOR_POSITION_LEVELS, max_pages, limit
            )
            # Internships are often tagged by employment type rather than level.
            # NOTE: only "Internship/Attachment" is a valid MCF employmentType value
            # ("Traineeship" 400s), so we filter to that and let classify() label the rest.
            results += await _fetch_pages(
                client, cats, ["Internship/Attachment"], [], max_pages, limit
            )

    return _dedupe(results)


def _dedupe(dtos: Iterable[JobDTO]) -> list[JobDTO]:
    seen: dict[str, JobDTO] = {}
    for d in dtos:
        seen.setdefault(d.source_job_id, d)
    return list(seen.values())
