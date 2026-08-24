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
    public_base_url: str = "http://localhost:8100"
    cors_origins: str = "http://localhost:3000"

    # --- Scheduler ---
    enable_scheduler: bool = True
    mcf_scrape_interval_min: int = 60
    company_scrape_interval_min: int = 240
    gmail_poll_interval_min: int = 5

    # --- Gmail ---
    gmail_credentials_file: str = "credentials.json"
    gmail_token_file: str = "token.json"
    gmail_dry_run: bool = False

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    @property
    def resolved_database_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{(BACKEND_DIR / 'jobtrack.sqlite').as_posix()}"
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
    def gmail_credentials_path(self) -> Path:
        return BACKEND_DIR / self.gmail_credentials_file

    @property
    def gmail_token_path(self) -> Path:
        return BACKEND_DIR / self.gmail_token_file

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


settings = Settings()
