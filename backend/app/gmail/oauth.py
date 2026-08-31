"""Gmail OAuth (read-only) and a thin service accessor.

One-time flow: run ``python -m app.gmail.oauth`` locally, which opens a browser, you grant
read-only access, and a refresh token is written to ``GMAIL_TOKEN_FILE``. In prod that
token file's contents go into an env var / secret and are materialised on boot.

Google libraries are imported lazily so the rest of the app runs even when Gmail isn't
configured yet.
"""
from __future__ import annotations

import logging
import os

from ..config import settings

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _ensure_token_file() -> None:
    """In prod the token isn't on disk (ephemeral) — seed it from the secret env var.

    ``GMAIL_TOKEN_JSON`` holds the authorized_user JSON (token, refresh_token, client_id,
    client_secret, ...), which is self-sufficient for silent refresh. We only write it
    when the file is missing so a locally-refreshed token is never clobbered.
    """
    token_path = settings.gmail_token_path
    # Also re-seed an EMPTY file: that's what a failed write leaves, and a zero-byte token
    # is no more usable than a missing one.
    has_content = token_path.exists() and token_path.stat().st_size > 0
    if has_content or not settings.gmail_token_json.strip():
        return
    _write_token(token_path, settings.gmail_token_json)
    log.info("Materialised Gmail token from GMAIL_TOKEN_JSON")


def _write_token(path, contents: str) -> None:
    """Write the token atomically: full temp file, then rename over the original.

    ``write_text`` truncates before writing, so a failure part-way — a full disk, most
    likely — leaves an EMPTY token behind and Gmail auth is dead until it's replaced by
    hand. Renaming within the same directory is atomic, so the old token survives any
    failure writing the new one.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(contents, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    _ensure_token_file()
    token_path = settings.gmail_token_path
    if not token_path.exists() or token_path.stat().st_size == 0:
        # An empty file is what a failed write leaves behind; treat it as "not authorized"
        # rather than letting a JSONDecodeError escape on every poll.
        if token_path.exists():
            log.error(
                "Gmail token at %s is empty — re-run `python -m app.gmail.oauth` and "
                "copy the file back", token_path,
            )
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except ValueError as exc:  # includes JSONDecodeError on a corrupt file
        log.error("Gmail token at %s is unreadable (%s); re-run the OAuth flow",
                  token_path, exc)
        return None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _write_token(token_path, creds.to_json())
    return creds


def get_service():
    """Return an authorized Gmail API service, or None if not configured."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("google-api-python-client not installed; Gmail disabled")
        return None

    try:
        creds = _load_credentials()
    except Exception:  # noqa: BLE001 - refresh failure, revoked grant, no network
        # Returning None degrades to "not configured"; letting this escape made the
        # scheduled poll throw a full traceback every 5 minutes, which is what filled the
        # disk that broke the token in the first place.
        log.exception("Gmail credentials could not be loaded; treating as unconfigured")
        return None
    if creds is None or not creds.valid:
        log.info("Gmail not authorized yet (run python -m app.gmail.oauth)")
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def is_connected() -> bool:
    """Whether a usable Gmail token exists, without building an API client.

    Used by ``GET /gmail/status`` so the dashboard can stop showing setup instructions
    once authorization is done. Never raises — a broken/absent token is just False.
    """
    try:
        creds = _load_credentials()
    except Exception:  # noqa: BLE001 - malformed token file, refresh failure, no network
        log.debug("Gmail credential check failed", exc_info=True)
        return False
    return bool(creds and creds.valid)


def run_local_oauth() -> None:
    """Interactive one-time authorization (local machine only)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = settings.gmail_credentials_path
    if not creds_path.exists():
        raise SystemExit(
            f"Missing {creds_path}. Download OAuth client secrets from Google Cloud "
            "Console (Desktop app) and save them there."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    settings.gmail_token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"Authorized. Token saved to {settings.gmail_token_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_local_oauth()
