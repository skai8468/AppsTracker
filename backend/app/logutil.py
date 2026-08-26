"""Logging setup that keeps secrets out of the log stream.

The Telegram Bot API embeds the bot token directly in the request URL
(``.../bot<token>/<method>``), so it shows up in httpx's per-request log line *and* in
any exception message that includes the URL (e.g. a failed request). A logger.setLevel
change only silences the routine request line, not exception text, so instead we redact
the token pattern from every record's rendered message before it reaches a handler
(journald, stdout, ...) — this covers both cases and any future code path.
"""
from __future__ import annotations

import logging
import re

_TOKEN_RE = re.compile(r"/bot\d+:[A-Za-z0-9_-]+")


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = _TOKEN_RE.sub("/bot<redacted>", msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactSecretsFilter())
