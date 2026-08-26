"""In-process APScheduler wiring for the recurring background job.

Runs inside the FastAPI process (fine at single-user scale on an always-on host):
  * Gmail poll — every ~5 minutes

The job is wrapped so an exception is logged, never crashing the scheduler thread.
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
