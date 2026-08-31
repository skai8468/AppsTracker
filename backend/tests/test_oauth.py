"""Gmail token handling — chiefly that a bad token degrades instead of exploding.

A full disk truncated token.json to zero bytes on the VM. Every poll then raised
JSONDecodeError, which both stopped all mail detection and wrote a traceback every five
minutes into the log that had filled the disk to begin with.
"""
from __future__ import annotations

import app.gmail.oauth as oauth


def _point_token_at(tmp_path, monkeypatch, name="token.json"):
    path = tmp_path / name
    monkeypatch.setattr(type(oauth.settings), "gmail_token_path",
                        property(lambda self: path))
    return path


def test_empty_token_reads_as_unauthorized(tmp_path, monkeypatch):
    path = _point_token_at(tmp_path, monkeypatch)
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(oauth.settings, "gmail_token_json", "")
    assert oauth._load_credentials() is None      # no JSONDecodeError


def test_corrupt_token_reads_as_unauthorized(tmp_path, monkeypatch):
    path = _point_token_at(tmp_path, monkeypatch)
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(oauth.settings, "gmail_token_json", "")
    assert oauth._load_credentials() is None


def test_missing_token_reads_as_unauthorized(tmp_path, monkeypatch):
    _point_token_at(tmp_path, monkeypatch)
    monkeypatch.setattr(oauth.settings, "gmail_token_json", "")
    assert oauth._load_credentials() is None


def test_is_connected_is_false_for_a_broken_token(tmp_path, monkeypatch):
    path = _point_token_at(tmp_path, monkeypatch)
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(oauth.settings, "gmail_token_json", "")
    assert oauth.is_connected() is False


def test_failed_write_leaves_the_existing_token_intact(tmp_path, monkeypatch):
    """The disk-full case: a doomed write must not destroy a working token."""
    path = tmp_path / "token.json"
    path.write_text('{"token": "original"}', encoding="utf-8")

    def _boom(self, *a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("pathlib.Path.write_text", _boom)
    try:
        oauth._write_token(path, '{"token": "replacement"}')
    except OSError:
        pass
    assert path.read_text(encoding="utf-8") == '{"token": "original"}'


def test_empty_token_is_reseeded_from_the_env_var(tmp_path, monkeypatch):
    """A zero-byte token is as useless as a missing one, so the secret must refill it."""
    path = _point_token_at(tmp_path, monkeypatch)
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(oauth.settings, "gmail_token_json", '{"token": "seeded"}')
    oauth._ensure_token_file()
    assert path.read_text(encoding="utf-8") == '{"token": "seeded"}'
