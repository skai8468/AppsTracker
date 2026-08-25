"""Telegram bot via **long-polling** (getUpdates).

A self-hosted always-on VM has no public HTTPS endpoint, so we pull updates instead of
receiving a webhook. A single daemon thread holds a long-poll request open (~50s) and
dispatches each update; the last processed ``update_id`` is persisted in the settings
table so a restart doesn't replay old messages. Only one getUpdates consumer may run at a
time, so we ``deleteWebhook`` on startup and use ``--workers 1`` for the API process.

Commands:
  * ``/start``  — capture the user's chat_id so notifications know where to go.
  * ``/status`` — summarise the open application pipeline.
  * ``/jobs``   — latest matching jobs.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import httpx
from sqlmodel import select

from ..config import settings
from ..db import get_setting, session_scope, set_setting
from ..models import Application, AppStatus, Job
from .notify import CHAT_ID_KEY, send_message

log = logging.getLogger(__name__)

OFFSET_KEY = "telegram_update_offset"
_API = "https://api.telegram.org/bot{token}/{method}"
_LONG_POLL_TIMEOUT = 50  # seconds Telegram holds the request open with no new updates

_thread: threading.Thread | None = None
_stop = threading.Event()


# --- command handling -------------------------------------------------------------

def _handle_update(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = str((message.get("chat") or {}).get("id", ""))
    text = (message.get("text") or "").strip()
    if not chat_id:
        return

    if text.startswith("/start"):
        with session_scope() as session:
            set_setting(session, CHAT_ID_KEY, chat_id)
        send_message(
            "👋 JobTrack SG connected! You'll get pings when:\n"
            "• an application is confirmed\n"
            "• a tracked company emails you\n\n"
            "Commands: /status  /jobs",
            chat_id=chat_id,
        )
    elif text.startswith("/status"):
        send_message(_status_summary(), chat_id=chat_id)
    elif text.startswith("/jobs"):
        send_message(_latest_jobs(), chat_id=chat_id)


def _status_summary() -> str:
    with session_scope() as session:
        apps = session.exec(select(Application)).all()
    if not apps:
        return "No applications tracked yet."
    by_status: dict[str, int] = {}
    for a in apps:
        by_status[a.status.value] = by_status.get(a.status.value, 0) + 1
    lines = ["📊 Your pipeline:"]
    for status in AppStatus:
        if status.value in by_status:
            lines.append(f"• {status.value}: {by_status[status.value]}")
    return "\n".join(lines)


def _latest_jobs(limit: int = 5) -> str:
    with session_scope() as session:
        jobs = session.exec(
            select(Job).where(Job.is_active == True)  # noqa: E712
            .order_by(Job.scraped_at.desc())
            .limit(limit)
        ).all()
    if not jobs:
        return "No jobs scraped yet."
    lines = ["🆕 Latest roles:"]
    for j in jobs:
        salary = ""
        if j.salary_min or j.salary_max:
            salary = f" (S${int(j.salary_min or 0)}–{int(j.salary_max or 0)}/{j.salary_period})"
        lines.append(f"• {j.title} @ {j.company_name}{salary}\n  {j.apply_url}")
    return "\n".join(lines)


# --- long-poll loop ---------------------------------------------------------------

def _delete_webhook() -> None:
    """getUpdates is rejected while a webhook is registered — clear any stale one."""
    try:
        httpx.get(
            _API.format(token=settings.telegram_bot_token, method="deleteWebhook"),
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        log.warning("deleteWebhook failed: %s", exc)


def _get_updates(offset: int | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": _LONG_POLL_TIMEOUT}
    if offset is not None:
        params["offset"] = offset
    resp = httpx.get(
        _API.format(token=settings.telegram_bot_token, method="getUpdates"),
        params=params,
        timeout=_LONG_POLL_TIMEOUT + 15.0,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def _poll_loop() -> None:
    with session_scope() as session:
        stored = get_setting(session, OFFSET_KEY)
    offset = int(stored) if stored else None
    log.info("Telegram long-poll started (offset=%s)", offset)

    while not _stop.is_set():
        try:
            updates = _get_updates(offset)
        except Exception as exc:  # noqa: BLE001 — network blips shouldn't kill the loop
            log.warning("getUpdates failed: %s", exc)
            _stop.wait(5)
            continue

        for update in updates:
            try:
                _handle_update(update)
            except Exception:  # noqa: BLE001 — one bad update shouldn't stop polling
                log.exception("failed to handle update %s", update.get("update_id"))
            offset = update["update_id"] + 1
            with session_scope() as session:
                set_setting(session, OFFSET_KEY, str(offset))


def start_polling() -> None:
    global _thread
    if not settings.telegram_enabled:
        log.info("Telegram disabled (no bot token); long-poll not started")
        return
    if _thread is not None and _thread.is_alive():
        return
    _delete_webhook()
    _stop.clear()
    _thread = threading.Thread(target=_poll_loop, name="telegram-longpoll", daemon=True)
    _thread.start()


def stop_polling() -> None:
    _stop.set()
