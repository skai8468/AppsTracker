"""Settings tests — chiefly the SQLite path fallback introduced by the AppsTracker rename."""
from __future__ import annotations

import app.config as config_module


def _sqlite_path_with(tmp_path, monkeypatch, existing: list[str]):
    """Point BACKEND_DIR at a temp dir containing `existing` db files, then resolve."""
    for name in existing:
        (tmp_path / name).write_bytes(b"")
    monkeypatch.setattr(config_module, "BACKEND_DIR", tmp_path)
    return config_module.Settings(database_url="").sqlite_path


def test_fresh_install_uses_new_name(tmp_path, monkeypatch):
    assert _sqlite_path_with(tmp_path, monkeypatch, []).name == "appstracker.sqlite"


def test_legacy_db_is_reused_when_new_one_absent(tmp_path, monkeypatch):
    """A pre-rename install must keep its data instead of silently starting empty."""
    assert (
        _sqlite_path_with(tmp_path, monkeypatch, ["jobtrack.sqlite"]).name
        == "jobtrack.sqlite"
    )


def test_new_name_wins_once_both_exist(tmp_path, monkeypatch):
    assert (
        _sqlite_path_with(
            tmp_path, monkeypatch, ["jobtrack.sqlite", "appstracker.sqlite"]
        ).name
        == "appstracker.sqlite"
    )


def test_explicit_database_url_bypasses_sqlite(monkeypatch):
    s = config_module.Settings(database_url="postgresql://u:p@h:5432/db")
    assert s.resolved_database_url == "postgresql+psycopg://u:p@h:5432/db"
