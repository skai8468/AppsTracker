"""Outbound Telegram messaging (raw Bot API via httpx — no heavy bot framework).

The user's chat_id is captured when they message the bot ``/start`` (see webhook.py) and
stored in the key/value settings table. ``send_notification`` is the single entry point
used by the Gmail poller for the two triggers the user asked for:
  1. application confirmed
  2. an email from a tracked company arrived
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from ..config import settings
from ..db import get_setting, session_scope

log = logging.getLogger(__name__)

CHAT_ID_KEY = "telegram_chat_id"
API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _chat_id() -> Optional[str]:
    with session_scope() as session:
        return get_setting(session, CHAT_ID_KEY)


def _call(method: str, payload: dict[str, Any]) -> bool:
    if not settings.telegram_enabled:
        log.info("Telegram disabled; would send: %s", payload.get("text"))
        return False
    url = API_BASE.format(token=settings.telegram_bot_token, method=method)
    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        resp.raise_for_status()
        return bool(resp.json().get("ok"))
    except httpx.HTTPError as exc:
        log.warning("Telegram %s failed: %s", method, exc)
        return False


def send_message(text: str, chat_id: Optional[str] = None,
                 reply_markup: Optional[dict] = None) -> bool:
    cid = chat_id or _chat_id()
    if not cid:
        log.info("No Telegram chat_id yet; user must /start the bot")
        return False
    payload: dict[str, Any] = {"chat_id": cid, "text": text, "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", payload)


def send_notification(text: str) -> bool:
    """Used by the poller. Confirmation messages go plain; company emails could later
    carry inline classify buttons (handled in webhook.py)."""
    return send_message(text)
