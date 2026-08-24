"""Database engine + session helpers, plus a tiny key/value settings accessor.

SQLModel/SQLAlchemy engine is created once from ``settings.resolved_database_url``.
SQLite (local dev) needs ``check_same_thread=False`` because APScheduler jobs and the
request handlers run on different threads.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings

_connect_args = {}
if settings.resolved_database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.resolved_database_url,
    echo=False,
    connect_args=_connect_args,
)


def init_db() -> None:
    """Create tables. Import models first so they register on SQLModel.metadata."""
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session per request."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for scheduler jobs and scripts."""
    with Session(engine) as session:
        yield session


# --- key/value settings helpers (Gmail historyId, Telegram chat_id, ...) ---

def get_setting(session: Session, key: str) -> Optional[str]:
    from .models import Setting

    row = session.get(Setting, key)
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    from .models import Setting

    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.commit()
