"""Example company scrapers.

These show the two common patterns:

1. Greenhouse-hosted boards (many tech firms) — one line via ``fetch_greenhouse``.
2. A custom-page placeholder for employers (e.g. local banks) whose careers site needs a
   bespoke parser or a headless browser.

Replace the board tokens below with real ones and add more modules over time. To find a
company's Greenhouse token, open its careers page and look for
``boards.greenhouse.io/<token>`` in the "apply" links.
"""
from __future__ import annotations

from ...models import Sector
from ..base import JobDTO
from . import register
from ._greenhouse import fetch_greenhouse

# --- Greenhouse examples (tokens are placeholders — swap for real ones) ---------------

@register("stripe")
async def stripe() -> list[JobDTO]:
    return await fetch_greenhouse("stripe", company_name="Stripe", sector=Sector.tech)


@register("databricks")
async def databricks() -> list[JobDTO]:
    return await fetch_greenhouse("databricks", company_name="Databricks", sector=Sector.tech)


# --- Custom-page placeholder ----------------------------------------------------------

@register("dbs")
async def dbs() -> list[JobDTO]:
    """DBS graduate/associate programmes.

    DBS's careers site is JS-rendered, so a real implementation would use the optional
    Playwright helper (see plan). Returns [] until implemented so it never breaks a pass.
    """
    return []
