# JobTrack SG

A personal job-search tracker for **fresh-grad roles, internships and management-associate
programmes** in Singapore's **tech** and **finance** sectors. It aggregates listings
(with links + salary), tracks your applications, watches your Gmail for confirmations and
recruiter replies, and pings a Telegram bot.

## What it does

- **Aggregates jobs** from [MyCareersFuture](https://www.mycareersfuture.gov.sg) (salary
  ranges included) + targeted company career pages (Greenhouse-hosted boards out of the
  box; add more per employer).
- **Classifies** each role by sector (tech/finance) and type (fresh-grad / internship /
  MA programme) and filters out senior roles.
- **Tracks applications** through a pipeline: applied → confirmed → interviewing →
  offer / rejected.
- **Watches Gmail** (read-only): auto-flips an application to *confirmed* when the
  confirmation email lands; surfaces any other email from a tracked company for you to
  one-tap classify.
- **Telegram notifications**: (1) application confirmed, (2) a tracked company emailed you.

## Architecture

A **single always-on FastAPI process** does everything: serves the REST API, serves the
statically-built **Next.js** dashboard from the same origin, runs the APScheduler scrape +
Gmail-poll jobs, and runs a **Telegram long-poll** bot (no webhook, so no public endpoint).
The database is **SQLite** on disk — plenty for one user. Designed to run on a small
always-on box (e.g. a GCP e2-micro); see [DEPLOY.md](DEPLOY.md).

```
backend/   FastAPI (API + serves the dashboard) + scrapers + Gmail poller + Telegram bot + APScheduler
frontend/  Next.js dashboard (Jobs / Applications / Inbox / Settings) — static-exported to frontend/out
```

## Local development

**Backend** (from `backend/`):
```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --port 8100 --reload               # API on http://localhost:8100
python -m app.scrapers.runner                           # one-off scrape into the DB
python -m pytest                                         # tests
```

**Frontend** (from `frontend/`):
```bash
npm install
cp .env.local.example .env.local     # points at http://localhost:8100
npm run dev                          # http://localhost:3000
```

## Connecting Gmail (read-only)

1. In Google Cloud Console, create an OAuth client (**Desktop app**), enable the **Gmail
   API**, and add yourself as a test user (keeps the app in *Testing* mode — no Google
   verification needed for a single user).
2. Download the client secrets to `backend/credentials.json`.
3. Run `python -m app.gmail.oauth` once — grants `gmail.readonly` and writes `token.json`.
4. On the VM, copy that `token.json` next to the app (the disk persists), or paste its
   contents into `GMAIL_TOKEN_JSON` and the app materialises it on boot.

Set `GMAIL_DRY_RUN=true` to log matches without changing state while testing.

## Connecting Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather); set `TELEGRAM_BOT_TOKEN`.
2. Start the app — it long-polls Telegram (`getUpdates`), so there's no webhook to
   register and no public endpoint to expose.
3. Message your bot `/start` to link your chat. Commands: `/status`, `/jobs`.

## Adding company scrapers

Drop a module in `backend/app/scrapers/companies/` and decorate an
`async def fetch() -> list[JobDTO]` with `@register("slug")`. Greenhouse boards are one
line via `fetch_greenhouse("<board-token>", company_name=...)`. Failures are isolated, so a
broken site never aborts a scrape pass.

## Deployment (single VM)

Runs as one always-on process on a small VM (built for a **GCP e2-micro / Debian**). The
backend serves both the API and the static dashboard; the dashboard is reached over an SSH
tunnel, so nothing is publicly exposed. `deploy/jobtrack.service` (systemd) and
`deploy/deploy.sh` (pull → build → restart) automate it. Full walkthrough in
[DEPLOY.md](DEPLOY.md).

## Notes & limitations

- The MyCareersFuture API is **undocumented** — isolated in one client with defensive
  parsing and back-off. `"Traineeship"` is not a valid employmentType filter (`"Internship/
  Attachment"` is).
- **Salary** is reliable only from MyCareersFuture; company-page jobs show "Not disclosed".
- **LinkedIn/Indeed are intentionally not scraped** (ToS + active blocking). Add such roles
  manually instead.
- Interview/offer/reject stages are **not auto-parsed** — you one-tap classify from the
  Inbox, which is far more reliable than parsing free-form email.
