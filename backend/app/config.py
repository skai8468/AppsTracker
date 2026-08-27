"""Application settings, loaded from environment / a local .env file.

All secrets and deploy-specific values live here so nothing is hard-coded. Local
development works with zero configuration: the database falls back to a SQLite file in
the backend directory, and the scheduler / integrations degrade gracefully when their
credentials are absent.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    # Empty => local SQLite file. Prod sets a postgresql+psycopg://... URL.
    database_url: str = ""

    # --- App ---
    cors_origins: str = "http://localhost:3000"
    # Path to the built Next.js static export (frontend/out). When present it's served at
    # / by this app, so the whole thing runs as a single process. Empty => auto-detect.
    frontend_dist: str = ""

    # --- Scheduler ---
    enable_scheduler: bool = True
    gmail_poll_interval_min: int = 5

    # --- Gmail ---
    gmail_credentials_file: str = "credentials.json"
    gmail_token_file: str = "token.json"
    gmail_dry_run: bool = False
    # Prod: the authorized_user token.json contents, injected as a secret. On boot the
    # app materialises this to gmail_token_file, since the container disk is ephemeral.
    gmail_token_json: str = ""

    # --- Telegram (long-polling; no webhook / public endpoint needed) ---
    telegram_bot_token: str = ""

    @property
    def sqlite_path(self) -> Path:
        """Local SQLite file, preferring the current name but honouring the legacy one.

        The app was renamed JobTrack SG -> AppsTracker. SQLite creates a missing file
        silently, so a bare rename would look like "all my applications vanished" rather
        than an error. Existing installs keep using ``jobtrack.sqlite`` until it's renamed;
        fresh ones get ``appstracker.sqlite``.
        """
        current = BACKEND_DIR / "appstracker.sqlite"
        legacy = BACKEND_DIR / "jobtrack.sqlite"
        if not current.exists() and legacy.exists():
            return legacy
        return current

    @property
    def resolved_database_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{self.sqlite_path.as_posix()}"
        url = self.database_url
        # Managed Postgres (Render/Railway/Heroku) hands out postgres:// or
        # postgresql:// URLs; SQLAlchemy + psycopg3 needs the +psycopg driver suffix.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def frontend_dist_path(self) -> Path:
        if self.frontend_dist:
            return Path(self.frontend_dist)
        return BACKEND_DIR.parent / "frontend" / "out"

    @property
    def gmail_credentials_path(self) -> Path:
        return BACKEND_DIR / self.gmail_credentials_file

    @property
    def gmail_token_path(self) -> Path:
        return BACKEND_DIR / self.gmail_token_file

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


settings = Settings()
