# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**AppsTracker** — a single-user job-application tracker for Singapore fresh-grad / intern /
management-associate roles. The user pastes a job link; the app tracks the application's
stage, watches Gmail read-only for confirmations and recruiter mail, and notifies via a
Telegram bot.

It is deliberately small: one user, one process, one SQLite file. Prefer the simple
solution that fits that scale over anything horizontally scalable.

## Architecture

One always-on FastAPI process does everything:

| Concern | Location |
|---|---|
| REST API | `backend/app/api/routes.py`, schemas in `schemas.py` |
| Static dashboard | mounted at `/` from `frontend/out` in `backend/app/main.py` |
| Gmail poll (every 5 min) | `backend/app/scheduler.py` → `backend/app/gmail/poller.py`, matching rules in `backend/app/gmail/matchers.py` |
| Telegram long-poll bot | `backend/app/telegram/bot.py`, sends via `notify.py` |
| Settings | `backend/app/config.py` (pydantic-settings, reads `backend/.env`) |
| ORM models | `backend/app/models.py` (SQLModel), session in `db.py` |
| Link metadata fetch | `backend/app/linkpreview.py` |
| Frontend | `frontend/` — Next.js 14 App Router, static export |

Deploy assets: `deploy/appstracker.service` (systemd) and `deploy/deploy.sh`
(pull → rebuild → restart). Walkthrough in [DEPLOY.md](DEPLOY.md).

## Commands

Backend, from `backend/`:

```bash
python -m pytest
```

```bash
uvicorn app.main:app --port 8100 --reload
```

Frontend, from `frontend/`:

```bash
npm run dev
```

The venv lives at `backend/.venv`. On Windows its executables are under
`backend/.venv/Scripts/`, not `bin/`.

## Gmail integration

Uses the **official Google API client** (`google-api-python-client` + `google-auth`)
against `gmail.googleapis.com` directly — no MCP server, no connector, no third party.

- Scope is `gmail.readonly` only. Never add a write scope; nothing in the app needs to
  modify or send mail.
- Auth is OAuth 2.0 installed-app flow, run once locally via `python -m app.gmail.oauth`.
  The refresh token lands in `backend/token.json` (or is seeded from the `GMAIL_TOKEN_JSON`
  env var on boot).
- Endpoints used: `users().getProfile`, `users().history().list` (incremental delta poll),
  `users().messages().get` with `format="metadata"`, and `users().messages().list` for the
  backfill path (`scan_recent`).
- Polling is incremental from a stored `historyId`. The first poll records current state
  and does **not** backfill; `POST /admin/scan-inbox?days=N` sweeps older mail.
- A confirmation from an untracked company still creates the company and the application
  (`process_message` in `poller.py`), gated by `settings.auto_track_from_email` (default
  on). `matchers.is_ats_domain` stops a shared ATS domain (Workday, Greenhouse, etc.) being
  claimed as that employer's own tracked domain.

**The token file is fragile and load-bearing.** Several past bugs came from corrupting it.
`_write_token` writes to a temp file and `os.replace`s it, because a truncating write that
fails part-way (full disk) leaves an empty token and kills Gmail auth until it is replaced
by hand. Keep writes atomic, and keep treating an empty/corrupt token as "not authorized"
rather than letting an exception escape into the 5-minute poll loop.

`get_service()` and `is_connected()` never raise — a broken token degrades to
"unconfigured". Preserve that; a raising poll job used to fill the disk with tracebacks.

## Conventions

- **Comments explain why, not what.** The existing code documents the failure that
  motivated a piece of defensive handling. Match that when adding similar code; do not add
  narration of what a line obviously does.
- Google/Telegram libraries are imported **lazily inside functions** so the app boots with
  those integrations unconfigured. Keep it that way.
- Broad `except Exception` is used intentionally at integration boundaries, with a
  `# noqa: BLE001` and a note on what it is absorbing. Do not widen it further inside
  business logic.
- Notifications pass `(id, payload)` tuples rather than ORM rows, because the commit
  beforehand expires session instances — a `DetachedInstanceError` fixed in commit
  `96dbedd`. Don't hand detached ORM objects to the notifier.
- Frontend calls the API through `frontend/lib/api.ts`; an empty `NEXT_PUBLIC_API_BASE`
  means same-origin relative paths, which is what the production build uses.

## Gotchas

- **Single worker is mandatory.** The scheduler and Telegram poller are in-process
  singletons. Two workers means double Gmail polls and Telegram `getUpdates` conflicts.
- **SQLite path fallback.** `Settings.sqlite_path` prefers `appstracker.sqlite` but falls
  back to an existing `jobtrack.sqlite`. SQLite creates a missing file silently, so
  removing that fallback would silently present an empty database rather than an error.
  Leave it in place.
- `next build` OOMs on a 1 GB VM without swap; `deploy.sh` also caps the Node heap.
- The service binds `0.0.0.0:8100`, not `127.0.0.1`, on purpose — the dashboard is reached
  over Tailscale (VM joins the user's tailnet), not an SSH tunnel, and no GCP firewall rule
  opens 8100 to the public internet. Don't "harden" this back to `127.0.0.1`; that would
  just break Tailscale access.
- Never commit `token.json`, `credentials.json`, `.env`, or the `.sqlite` files — all are
  git-ignored.
