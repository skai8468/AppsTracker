"""Registry of per-company career-page scrapers.

Each scraper is an async ``fetch() -> list[JobDTO]`` registered via ``@register``. They're
isolated so one broken site can't take down a scrape pass — ``runner.py`` wraps each call
in try/except. Add a new employer by dropping a module in this package and decorating its
fetch function.

Company pages rarely publish salary, so those JobDTOs typically leave salary empty (the UI
shows "Not disclosed"). MyCareersFuture remains the salary-rich source.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Awaitable, Callable

from ..base import JobDTO

log = logging.getLogger(__name__)

CompanyFetcher = Callable[[], Awaitable[list[JobDTO]]]
_REGISTRY: dict[str, CompanyFetcher] = {}


def register(slug: str) -> Callable[[CompanyFetcher], CompanyFetcher]:
    def deco(fn: CompanyFetcher) -> CompanyFetcher:
        _REGISTRY[slug] = fn
        return fn

    return deco


def _load_all() -> None:
    """Import every sibling module so their @register decorators run."""
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{mod.name}")


def all_fetchers() -> dict[str, CompanyFetcher]:
    _load_all()
    return dict(_REGISTRY)
