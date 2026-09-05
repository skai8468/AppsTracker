# Deploying AppsTracker

Target: a single small always-on VM (built and tested on a **GCP e2-micro / Debian 12**).
Everything runs as **one process**:

- FastAPI serves the **REST API** *and* the **static dashboard** on one port (`8100`).
- APScheduler runs the **Gmail poll** in-process (every 5 min by default).
- A **Telegram long-poll** thread pulls updates — no webhook, so no public HTTPS needed.
- **SQLite** on the VM disk is the database (single user — no Postgres to run).

Nothing is exposed to the public internet: no GCP firewall rule opens a port, no TLS, no
domain. The bot dials out to Telegram; you reach the dashboard over **Tailscale** — the VM
and your devices join the same private tailnet, and the dashboard is just a URL on it.

```
you (on your tailnet) ──http://<vm-tailscale-ip>:8100──▶ VM :8100 ──▶ FastAPI ─┬─ /              (dashboard)
                                                                               ├─ /applications  (API)
                                                                               ├─ APScheduler    (Gmail poll)
                                                                               └─ Telegram long-poll
```

---

## Before you start

Collect these three things on your **laptop** — the deploy stalls without them, and two of
them cannot be produced on a headless VM.

| # | What | Where it comes from |
|---|------|---------------------|
| 1 | Telegram bot token | @BotFather → `/newbot` |
| 2 | `backend/credentials.json` | Google Cloud OAuth client (Desktop app) |
| 3 | `backend/token.json` | running the OAuth flow locally, once |

### 1. Telegram bot token

Message **[@BotFather](https://t.me/BotFather)** → `/newbot` → copy the token it gives you.
That is the only Telegram secret (long-polling needs no webhook secret).

### 2 + 3. Gmail read-only token

The OAuth consent step opens a browser, so it must run on your laptop, not the VM.

1. [Google Cloud Console](https://console.cloud.google.com/) → create a project → enable
   the **Gmail API**.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app**.
   Download the JSON to `backend/credentials.json`.
3. On the **OAuth consent screen**, add your own Google account as a **Test user**. Staying
   in *Testing* mode is fine — you are the only user, and it avoids Google verification.
4. Run the one-time flow from the repo:

```bash
cd backend && python -m venv .venv && ./.venv/Scripts/pip.exe install -r requirements.txt && ./.venv/Scripts/python.exe -m app.gmail.oauth
```

(On macOS/Linux use `./.venv/bin/pip` and `./.venv/bin/python`.) A browser opens, you grant
**read-only** Gmail access, and `backend/token.json` is written. You copy that file to the
VM in step 5.

> `token.json` holds a long-lived refresh token — treat it as a password. It is
> git-ignored; never commit it.

---

## 1. Create the VM

GCP Console → Compute Engine → **Create instance**:

- Machine type **e2-micro**, in a free-tier region (e.g. `us-central1`) for the always-free
  allowance.
- Boot disk **Debian 12 (bookworm)**, 10–30 GB standard disk.
- **No firewall rules** — we open no ports. SSH in via the Console or `gcloud compute ssh`.

## 2. Base packages

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git curl
```

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

Verify: `python3 --version` (3.11+) and `node --version` (v20).

Install Tailscale and join it to your tailnet — this is how you'll reach the dashboard
later, instead of an SSH tunnel or a public IP:

```bash
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
```

The command prints a login URL; open it on your laptop to authorize the VM. Note the
Tailscale IP it's assigned (`tailscale ip -4`, or the MagicDNS name shown in the
[admin console](https://login.tailscale.com/admin/machines)) — you'll use it in step 9.

## 3. Add swap — required on a 1 GB VM

`next build` is memory-hungry and will OOM on an e2-micro without swap.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Verify: `free -h` shows a 2 GB swap line.

## 4. Service user + code

```bash
sudo useradd -r -m -d /opt/appstracker -s /usr/sbin/nologin appstracker || true
```

```bash
sudo git clone https://github.com/skai8468/AppsTracker.git /opt/appstracker && sudo chown -R appstracker:appstracker /opt/appstracker
```

## 5. Configuration + the Gmail token

```bash
sudo -u appstracker cp /opt/appstracker/backend/.env.example /opt/appstracker/backend/.env
```

```bash
sudo -u appstracker nano /opt/appstracker/backend/.env
```

Set **`TELEGRAM_BOT_TOKEN`**. Everything else has a working default — in particular leave
`DATABASE_URL` empty to use SQLite.

Then copy the token from your **laptop**:

```bash
scp backend/token.json <you>@<vm>:/tmp/token.json
```

Back on the VM, move it into place:

```bash
sudo mv /tmp/token.json /opt/appstracker/backend/token.json && sudo chown appstracker:appstracker /opt/appstracker/backend/token.json && sudo chmod 600 /opt/appstracker/backend/token.json
```

`credentials.json` is only needed for the interactive OAuth flow — the VM does not need it.

## 6. Install the systemd unit

```bash
sudo cp /opt/appstracker/deploy/appstracker.service /etc/systemd/system/appstracker.service && sudo systemctl daemon-reload && sudo systemctl enable appstracker
```

Enable only — do not start it yet, nothing is built.

## 7. First build + start

```bash
sudo /opt/appstracker/deploy/deploy.sh
```

This creates the venv, installs deps, builds the frontend into `frontend/out`, and starts
the service. Watch it come up:

```bash
journalctl -u appstracker -f
```

Expect `AppsTracker backend ready`, `Serving dashboard from ...`, `Scheduler started` and
`Telegram long-poll started`. Then confirm the API answers:

```bash
curl localhost:8100/health && curl localhost:8100/gmail/status
```

You want `{"status":"ok"}` and `{"connected":true}`. A `false` there means the token did not
land — recheck step 5.

## 8. Link Telegram

Message your bot **`/start`**. It stores your chat_id in SQLite (survives restarts). Try
`/status` and `/jobs`. Notifications fire when (1) an application is confirmed, (2) a
tracked company emails you.

## 9. Open the dashboard

From any device on your tailnet (laptop or phone, with Tailscale installed and signed in
to the same account), open `http://<vm-tailscale-ip>:8100` — or the MagicDNS name if
you've enabled it, e.g. `http://appstracker:8100`. Dashboard and API are both served from
there; nothing outside the tailnet can reach port 8100.

## 10. Backfill older mail (optional)

The first Gmail poll only records the current mailbox state — it does not look backwards.
To sweep mail that arrived before Gmail was connected:

```bash
curl -X POST 'localhost:8100/admin/scan-inbox?days=30'
```

---

## Updating later

```bash
sudo /opt/appstracker/deploy/deploy.sh
```

Pull → rebuild → restart, and safe to re-run.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `next build` killed during deploy | Out of memory. Confirm swap is on (`free -h`, step 3). Still failing? Build on your laptop with `NEXT_PUBLIC_API_BASE= npm run build` and `rsync frontend/out/` to `/opt/appstracker/frontend/out/` — the VM then needs only Python. |
| Logs say `running API-only` | `frontend/out` is missing, so the frontend build failed. Re-run `deploy.sh` and read the build output. |
| `/gmail/status` returns `connected: false` | `token.json` is missing, empty, or unreadable. The logs name the exact file and reason. Re-run the OAuth flow on your laptop and re-copy it. |
| Gmail stops working after months | Google revoked the grant (password change, or a Testing-mode app idle > 6 months). Re-run the OAuth flow locally and re-copy `token.json`. |
| Telegram bot silent | `TELEGRAM_BOT_TOKEN` unset in `backend/.env`, or another process is long-polling the same bot — only one `getUpdates` consumer is allowed. |
| Service won't start | `journalctl -u appstracker -n 50`. Usually a missing or stale venv; `deploy.sh` rebuilds it. |
| Can't reach the dashboard over Tailscale | Confirm the VM shows up in `tailscale status` on your laptop, and that `sudo tailscale up` was run on the VM (check with `tailscale status` there too). Also confirm the service is actually listening on all interfaces: `ss -tlnp \| grep 8100` should show `0.0.0.0:8100`, not `127.0.0.1:8100`. |

## Notes

- **Single worker only.** The unit runs `uvicorn --workers 1` deliberately: the scheduler
  and Telegram poller are in-process singletons. More workers means duplicate Gmail polls
  and Telegram `getUpdates` conflicts.
- **Backups.** The database is one file, `backend/appstracker.sqlite`. `cp` it (or use
  `sqlite3 .backup`) on a cron.
- **Safe first run.** Set `GMAIL_DRY_RUN=true` in `.env` to have the poller log matches
  without changing any application state.
- **Going public.** If you ever want the dashboard reachable without Tailscale, put Caddy in
  front for automatic TLS — but that needs a domain and an open port, which this setup
  deliberately avoids.
