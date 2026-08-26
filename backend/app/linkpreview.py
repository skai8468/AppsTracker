"""Best-effort role/company extraction from a pasted job URL.

The user pastes a single job link and we try to pre-fill the title + company so they don't
have to type them. This is a single, user-triggered fetch (not a crawler): we GET one page
and parse it. Extraction is deliberately layered from most to least reliable:

  1. JSON-LD ``JobPosting`` structured data (title + hiringOrganization.name) — emitted by
     most ATS boards (Greenhouse/Lever/Ashby/Workday) and many career pages.
  2. Open Graph / meta tags (og:title, og:site_name).
  3. The <title> element.

Anything that fails (JS-only pages, bot-blocking sites like LinkedIn/Indeed, timeouts)
yields ``ok=False`` and the frontend simply leaves the fields blank for manual entry.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
_MAX_BYTES = 2_000_000  # cap the response we parse

_TECH_KW = (
    "software", "engineer", "developer", "data", "machine learning", " ml ", " ai ",
    "devops", "security", "cloud", "backend", "frontend", "full stack", "fullstack",
    "sre", "platform", "infrastructure", "programmer", "computer",
)
_FIN_KW = (
    "bank", "finance", "financial", "investment", "trading", "trader", "quant", "risk",
    "audit", "actuar", "wealth", "asset management", "equity", "capital", "markets",
    "portfolio", "treasury", "accounting",
)


def guess_sector(title: str, company: str) -> str:
    blob = f" {title} {company} ".lower()
    if any(k in blob for k in _FIN_KW):
        return "finance"
    if any(k in blob for k in _TECH_KW):
        return "tech"
    return "other"


def _iter_jsonld(tree: HTMLParser):
    """Yield every JSON object embedded in <script type=application/ld+json>, flattening
    top-level arrays and @graph containers."""
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    stack.extend(item["@graph"])
                yield item


def _jsonld_jobposting(tree: HTMLParser) -> tuple[Optional[str], Optional[str]]:
    for obj in _iter_jsonld(tree):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if "JobPosting" not in types:
            continue
        title = obj.get("title")
        org = obj.get("hiringOrganization")
        company: Optional[str] = None
        if isinstance(org, dict):
            company = org.get("name")
        elif isinstance(org, str):
            company = org
        if title:
            return (str(title).strip(), str(company).strip() if company else None)
    return (None, None)


def _meta(tree: HTMLParser, prop: str) -> Optional[str]:
    for sel in (f'meta[property="{prop}"]', f'meta[name="{prop}"]'):
        node = tree.css_first(sel)
        if node:
            val = node.attributes.get("content")
            if val and val.strip():
                return val.strip()
    return None


def _clean_title(title: str, company: Optional[str]) -> str:
    """Trim common '<role> - <company>' / '| <company>' / 'at <company>' noise."""
    title = title.strip()
    if company:
        for sep in (f" - {company}", f" | {company}", f" at {company}", f" @ {company}"):
            if title.lower().endswith(sep.lower()):
                title = title[: -len(sep)].strip()
    # Fall back: cut at the last separator if the tail looks like a site name.
    for sep in (" | ", " – ", " — "):
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    return title


def parse_meta(html: str, url: str = "") -> dict[str, Any]:
    """Pure (no network) extraction. Returns {title, company, sector, ok}."""
    tree = HTMLParser(html or "")

    title, company = _jsonld_jobposting(tree)

    if not company:
        company = _meta(tree, "og:site_name")
    if not title:
        title = _meta(tree, "og:title")
    if not title:
        node = tree.css_first("title")
        if node:
            title = node.text(strip=True)

    title = _clean_title(title, company) if title else ""
    company = (company or "").strip()
    ok = bool(title)
    return {
        "title": title,
        "company": company,
        "sector": guess_sector(title, company),
        "ok": ok,
    }


def fetch_meta(url: str) -> dict[str, Any]:
    """Fetch the URL and extract job metadata. Best-effort: any failure -> ok=False."""
    empty = {"title": "", "company": "", "sector": "other", "ok": False}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return empty
    try:
        import httpx

        with httpx.Client(
            follow_redirects=True,
            timeout=8.0,
            headers={"User-Agent": _UA, "Accept": "text/html"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text[:_MAX_BYTES]
    except Exception as exc:  # noqa: BLE001 — network/parse issues degrade to manual entry
        log.info("link preview failed for %s: %s", url, exc)
        return empty
    return parse_meta(html, url)
