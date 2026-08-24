"""Telegram webhook endpoint + command handling.

Telegram calls POST ``/telegram/webhook/{secret}`` for every update (webhook mode — no
long-polling, which suits an always-on host). We handle:
  * ``/start``  — capture the user's chat_id so notifications know where to go.
  * ``/status`` — summarise the open application pipeline.
  * ``/jobs``   — latest matching jobs.

Set the webhook once after deploy:
    POST https://api.telegram.org/bot<token>/setWebhook
         ?url=<PUBLIC_BASE_URL>/telegram/webhook/<secret>
(see set_webhook() helper / __main__).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import select

from ..config import settings
from ..db import session_scope, set_setting
from ..models import Application, AppStatus, Job
from .notify import CHAT_ID_KEY, send_message

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.telegram_webhook_secret or not settings.telegram_webhook_secret:
        raise HTTPException(403, "bad webhook secret")
    update = await request.json()
    _handle_update(update)
    return {"ok": True}


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


def set_webhook() -> dict[str, Any]:
    """Register the webhook URL with Telegram (call once after deploy)."""
    import httpx

    url = (
        f"{settings.public_base_url}/telegram/webhook/{settings.telegram_webhook_secret}"
    )
    resp = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
        json={"url": url},
        timeout=15.0,
    )
    return resp.json()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(set_webhook())
