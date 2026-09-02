# AppsTracker

A personal job-application tracker for **fresh-grad roles, internships and
management-associate programmes** in Singapore's **tech** and **finance** sectors. You
paste the link to a job you care about; it tracks whether you've applied and how long it's
been, watches your Gmail for confirmations and recruiter replies, and pings a Telegram bot.

## What it does

- **Track by link**: paste a job URL and it best-effort **auto-detects the role + company**
  (JSON-LD / Open Graph / `<title>`), which you confirm and save. No scraping, no catalog —
  only the jobs you choose.
- **Pipeline**: each application moves through *Saved → Applied → Confirmed → Interviewing →
  Offer → Rejected*, showing **how long since you applied**.
- **Watches Gmail** (read-only): auto-flips an application to *confirmed* when the
  confirmation email lands; surfaces any other email from a tracked company for you to
  one-tap classify.
- **Telegram notifications**: (1) application confirmed, (2) a tracked company emailed you.

## Architecture

A **single always-on FastAPI process** does everything: serves the REST API, serves the
statically-built **Next.js** dashboard from the same origin, runs the Gmail poll
(APScheduler, every 5 min), and runs a **Telegram long-poll** bot (no webhook, so no public
endpoint). The database is **SQLite** on disk — plenty for one user. Designed to run on a
small always-on box (e.g. a GCP e2-micro); see [DEPLOY.md](DEPLOY.md).

```
backend/   FastAPI (API + serves the dashboard) + link preview + Gmail poller + Telegram bot + APScheduler
frontend/  Next.js dashboard (Applications / Inbox / Settings) — static-exported to frontend/out
```

Gmail is read via the **official Google API client** (`google-api-python-client`) over
plain OAuth 2.0 with the `gmail.readonly` scope — no third-party service sits in between.

## Local development

**Backend** (from `backend/`):

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash; .venv/bin/activate on *nix
```

```bash
pip install -r requirements.txt && cp .env.example .env
```

```bash
uvicorn app.main:app --port 8100 --reload
```

The API is then on <http://localhost:8100>. Run the tests with:

```bash
python -m pytest
```

**Frontend** (from `frontend/`):

```bash
npm install && cp .env.local.example .env.local
```

```bash
npm run dev
```

Dashboard on <http://localhost:3000>, pointed at the backend on `:8100`.

## Connecting Gmail (read-only)

1. In Google Cloud Console, create an OAuth client (**Desktop app**), enable the **Gmail
   API**, and add yourself as a test user (keeps the app in *Testing* mode — no Google
   verification needed for a single user).
2. Download the client secrets to `backend/credentials.json`.
3. Run `python -m app.gmail.oauth` once — grants `gmail.readonly` and writes `token.json`.
4. On the VM, copy that `token.json` next to the app (the disk persists), or paste its
   contents into `GMAIL_TOKEN_JSON` and the app materialises it on boot.

Set `GMAIL_DRY_RUN=true` to log matches without changing state while testing.

The first poll only records the current mailbox state — it does not backfill. To sweep mail
that arrived earlier, `POST /admin/scan-inbox?days=30`.

## Connecting Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather); set `TELEGRAM_BOT_TOKEN`.
2. Start the app — it long-polls Telegram (`getUpdates`), so there's no webhook to
   register and no public endpoint to expose.
3. Message your bot `/start` to link your chat. Commands: `/status`, `/jobs`.

## Deployment (single VM)

Runs as one always-on process on a small VM (built for a **GCP e2-micro / Debian**). The
backend serves both the API and the static dashboard; the dashboard is reached over an SSH
tunnel, so nothing is publicly exposed. `deploy/appstracker.service` (systemd) and
`deploy/deploy.sh` (pull → build → restart) automate it. Full walkthrough in
[DEPLOY.md](DEPLOY.md).

## Notes & limitations

- **No job-board scraping.** LinkedIn, Indeed and the like are intentionally not scraped
  (ToS + active blocking). You add roles by pasting their link, and the app fetches only
  that page's metadata to prefill the title and company.
- **Salary is not tracked** — job pages rarely publish it reliably.
- Interview/offer/reject stages are **not auto-parsed** — you one-tap classify from the
  Inbox, which is far more reliable than parsing free-form email.
- **Single worker.** The scheduler and Telegram poller are in-process singletons; running
  more than one worker duplicates them.
