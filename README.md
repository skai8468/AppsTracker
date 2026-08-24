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

Single always-on **FastAPI** service (REST API + Telegram webhook + APScheduler jobs for
scraping and Gmail polling) backed by **Postgres** (SQLite locally), plus a **Next.js**
dashboard. See `../.claude/plans/` or the sections below.

```
backend/   FastAPI + scrapers + Gmail poller + Telegram bot + APScheduler
frontend/  Next.js dashboard (Jobs / Applications / Inbox / Settings)
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
4. In prod, put `token.json`'s contents into a secret and materialise it on boot.

Set `GMAIL_DRY_RUN=true` to log matches without changing state while testing.

## Connecting Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather); set `TELEGRAM_BOT_TOKEN` and a
   random `TELEGRAM_WEBHOOK_SECRET`.
2. After deploy, register the webhook: `python -m app.telegram.webhook`.
3. Message your bot `/start` to link your chat. Commands: `/status`, `/jobs`.

## Adding company scrapers

Drop a module in `backend/app/scrapers/companies/` and decorate an
`async def fetch() -> list[JobDTO]` with `@register("slug")`. Greenhouse boards are one
line via `fetch_greenhouse("<board-token>", company_name=...)`. Failures are isolated, so a
broken site never aborts a scrape pass.

## Deployment (Render)

`render.yaml` is a blueprint for two always-on web services (backend + frontend) plus
managed Postgres. After the first deploy, fill the `sync:false` env vars
(`PUBLIC_BASE_URL`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_BASE`, Telegram secrets), then run the
Telegram `setWebhook` step. Railway works the same way with the backend `Dockerfile`.

## Notes & limitations

- The MyCareersFuture API is **undocumented** — isolated in one client with defensive
  parsing and back-off. `"Traineeship"` is not a valid employmentType filter (`"Internship/
  Attachment"` is).
- **Salary** is reliable only from MyCareersFuture; company-page jobs show "Not disclosed".
- **LinkedIn/Indeed are intentionally not scraped** (ToS + active blocking). Add such roles
  manually instead.
- Interview/offer/reject stages are **not auto-parsed** — you one-tap classify from the
  Inbox, which is far more reliable than parsing free-form email.
