"""In-process APScheduler wiring for the three recurring background jobs.

Runs inside the FastAPI process (fine at single-user scale on an always-on host):
  * MCF scrape        — hourly (configurable)
  * company scrape    — every few hours
  * Gmail poll        — every ~5 minutes

Each job is wrapped so an exception is logged, never crashing the scheduler thread.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _safe(fn):
    def wrapper():
        try:
            result = fn()
            log.info("%s -> %s", fn.__name__, result)
        except Exception as exc:  # noqa: BLE001
            log.exception("scheduled job %s failed: %s", fn.__name__, exc)

    wrapper.__name__ = fn.__name__
    return wrapper


def _run_mcf_scrape():
    from .scrapers.runner import run_scrape

    return run_scrape()


def _run_company_scrape():
    # Company modules are included in run_scrape(); a separate hook lets us tune cadence
    # independently later. For now it shares the same pass.
    from .scrapers.runner import run_scrape

    return run_scrape()


def _run_gmail_poll():
    from .gmail.poller import poll_once

    return poll_once()


def start_scheduler() -> None:
    global _scheduler
    if not settings.enable_scheduler:
        log.info("Scheduler disabled via config")
        return
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _safe(_run_mcf_scrape),
        "interval",
        minutes=settings.mcf_scrape_interval_min,
        id="mcf_scrape",
        next_run_time=None,  # don't run immediately on boot
    )
    _scheduler.add_job(
        _safe(_run_gmail_poll),
        "interval",
        minutes=settings.gmail_poll_interval_min,
        id="gmail_poll",
    )
    _scheduler.start()
    log.info("Scheduler started")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
