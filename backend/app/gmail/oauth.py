"""Gmail OAuth (read-only) and a thin service accessor.

One-time flow: run ``python -m app.gmail.oauth`` locally, which opens a browser, you grant
read-only access, and a refresh token is written to ``GMAIL_TOKEN_FILE``. In prod that
token file's contents go into an env var / secret and are materialised on boot.

Google libraries are imported lazily so the rest of the app runs even when Gmail isn't
configured yet.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = settings.gmail_token_path
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_service():
    """Return an authorized Gmail API service, or None if not configured."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        log.warning("google-api-python-client not installed; Gmail disabled")
        return None

    creds = _load_credentials()
    if creds is None or not creds.valid:
        log.info("Gmail not authorized yet (run python -m app.gmail.oauth)")
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


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
