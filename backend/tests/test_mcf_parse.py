"""MyCareersFuture parsing tests — recorded JSON, no live calls."""
from __future__ import annotations

import json
from pathlib import Path

from app.models import JobType, Sector
from app.scrapers.mycareersfuture import parse_results

FIXTURE = Path(__file__).parent / "fixtures" / "mcf_sample.json"


def _load():
    return parse_results(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_parses_all_rows():
    dtos = _load()
    assert len(dtos) == 3


def test_salary_and_url_populated():
    dtos = {d.source_job_id: d for d in _load()}
    grad = dtos["MCF-2024-0001"]
    assert grad.salary_min == 4500
    assert grad.salary_max == 6000
    assert grad.salary_period == "month"
    assert grad.apply_url == "https://www.mycareersfuture.gov.sg/job/MCF-2024-0001"


def test_url_constructed_when_missing():
    dtos = {d.source_job_id: d for d in _load()}
    intern = dtos["MCF-2024-0002"]  # no jobDetailsUrl in fixture
    assert intern.apply_url.endswith("MCF-2024-0002")


def test_classification():
    dtos = {d.source_job_id: d for d in _load()}
    assert dtos["MCF-2024-0001"].sector == Sector.tech
    assert dtos["MCF-2024-0001"].job_type == JobType.grad
    assert dtos["MCF-2024-0002"].sector == Sector.finance
    assert dtos["MCF-2024-0002"].job_type == JobType.internship
    assert dtos["MCF-2024-0003"].job_type == JobType.ma_program
