# Deploying AppsTracker on a GCP e2-micro (Debian)

The whole app runs as **one always-on process** on a single small VM:

- FastAPI serves the **REST API** *and* the **static dashboard** from one port (`8100`).
- APScheduler runs the **scrapers + Gmail poller** in-process.
- A **Telegram long-poll** thread pulls updates (no webhook, so no public HTTPS needed).
- **SQLite** on the VM disk is the database (single user — no Postgres to run).

Access is via an **SSH tunnel**, so nothing is exposed to the internet: no open ports, no
TLS, no domain. The bot reaches out to Telegram; you reach the dashboard through SSH.

```
you ──ssh -L 8100:localhost:8100──▶ VM :8100 ──▶ FastAPI ─┬─ /            (dashboard)
                                                          ├─ /jobs, ...   (API)
                                                          ├─ APScheduler  (scrape + Gmail)
                                                          └─ Telegram long-poll
```

Sizing note: `next build` is memory-hungry; a 1 GB e2-micro needs **swap** (step 3) or it
will OOM. Everything else fits comfortably.

---

## 0. Local prep (once)

You need two things ready before touching the VM:

**a. Telegram bot token** — message **@BotFather** → `/newbot` → copy the token. That's the
only Telegram secret now (long-polling needs no webhook secret).

**b. Gmail read-only OAuth token** — the browser OAuth step must run on a machine with a
browser, i.e. your laptop, not the headless VM:
1. Google Cloud Console → new project → enable the **Gmail API**.
2. **Credentials → Create → OAuth client ID → Desktop app** → download JSON to
   `backend/credentials.json`. Add your Google account as a **Test user** on the consent
   screen (staying in "Testing" mode is fine — you're the only user).
3. Run the one-time flow locally:
   ```bash
   cd backend
   ./.venv/Scripts/python.exe -m app.gmail.oauth   # Windows; use ./.venv/bin/python on *nix
   ```
   This writes `backend/token.json`. You'll copy that file to the VM in step 5.

---

## 1. Create the VM
GCP Console → Compute Engine → **Create instance**:
- Machine type **e2-micro**, region a free-tier one (e.g. `us-central1`) if you want the
  always-free allowance.
- Boot disk **Debian 12 (bookworm)**, 10–30 GB standard disk.
- Allow no special firewall (we don't open any ports). SSH in via the Console or `gcloud`.

## 2. Base packages
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
# Node 20 (for `next build`)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## 3. Add swap (important on 1 GB)
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 4. Get the code + a service user
```bash
sudo useradd -r -m -d /opt/appstracker -s /usr/sbin/nologin appstracker || true
sudo git clone https://github.com/skai8468/appstracker.git /opt/appstracker
sudo chown -R appstracker:appstracker /opt/appstracker
```

## 5. Configure secrets + copy the Gmail token
```bash
sudo -u appstracker cp /opt/appstracker/backend/.env.example /opt/appstracker/backend/.env
sudo -u appstracker nano /opt/appstracker/backend/.env      # set TELEGRAM_BOT_TOKEN
```
From your **laptop**, copy the token you generated in step 0b:
```bash
scp backend/token.json <you>@<vm>:/tmp/token.json
# on the VM:
sudo mv /tmp/token.json /opt/appstracker/backend/token.json
sudo chown appstracker:appstracker /opt/appstracker/backend/token.json
```
(SQLite needs no config — it's the default. Leave `DATABASE_URL` empty.)

## 6. Install the service unit (before the first build)
```bash
sudo cp /opt/appstracker/deploy/appstracker.service /etc/systemd/system/appstracker.service
sudo systemctl daemon-reload
sudo systemctl enable appstracker        # enable, don't start yet — nothing is built
```

## 7. First build + start
```bash
sudo /opt/appstracker/deploy/deploy.sh   # builds venv + frontend, then starts the service
journalctl -u appstracker -f                # expect "backend ready" + "Telegram long-poll started"
```

## 8. Connect Telegram
Message your bot **`/start`** — it captures your chat_id (stored in SQLite, survives
restarts). Try `/status` and `/jobs`. Notifications fire on (1) an application confirmed,
(2) a tracked company emailing you.

## 9. Open the dashboard (SSH tunnel)
From your laptop:
```bash
ssh -L 8100:localhost:8100 <you>@<vm>
```
Then open <http://localhost:8100> in your browser. The dashboard and API both come through
the tunnel; nothing is exposed publicly.

---

## Updating later
```bash
ssh <you>@<vm>
sudo /opt/appstracker/deploy/deploy.sh   # pull, rebuild, restart
```
If `next build` ever OOMs despite swap, build the frontend on your laptop
(`NEXT_PUBLIC_API_BASE= npm run build`) and `rsync frontend/out/` to
`/opt/appstracker/frontend/out/` instead — the VM then needs only Python.

## Migrating an existing "JobTrack SG" install

Only needed once, on a VM provisioned before the rename. A `git pull` alone can't do this —
the systemd unit, the Linux user and the `/opt` directory all carry the old name.

Push the renamed code to GitHub **first** — the new unit file and deploy script have to be
in the checkout before they can be installed.

```bash
# 1. stop the old service and back up the database
sudo systemctl stop jobtrack && sudo systemctl disable jobtrack
sudo cp /opt/jobtrack-sg/backend/jobtrack.sqlite ~/appstracker-backup.sqlite

# 2. rename the directory, the user and the group
sudo mv /opt/jobtrack-sg /opt/appstracker
sudo usermod -l appstracker -d /opt/appstracker jobtrack
sudo groupmod -n appstracker jobtrack
sudo chown -R appstracker:appstracker /opt/appstracker

# 3. pull the renamed code BEFORE installing the unit — deploy/appstracker.service and the
#    updated deploy.sh only exist after this. (Set the remote first if you renamed the repo.)
sudo -u appstracker git -C /opt/appstracker remote set-url origin <new-url>
sudo -u appstracker git -C /opt/appstracker pull --ff-only

# 4. drop the venv — it hardcodes the OLD absolute path in every script's shebang, so
#    after the mv `.venv/bin/pip` dies with "cannot execute: required file not found"
#    (that means the *interpreter* is gone, not pip). deploy.sh rebuilds it.
sudo -u appstracker rm -rf /opt/appstracker/backend/.venv

# 5. install the new unit and start
sudo rm /etc/systemd/system/jobtrack.service
sudo cp /opt/appstracker/deploy/appstracker.service /etc/systemd/system/appstracker.service
sudo systemctl daemon-reload && sudo systemctl enable appstracker
sudo /opt/appstracker/deploy/deploy.sh
```

The database file is **left alone on purpose**. The app prefers `appstracker.sqlite` but
falls back to an existing `jobtrack.sqlite`, so your data keeps working untouched. SQLite
creates a missing file silently rather than erroring, so renaming it without that fallback
would look like every tracked application had vanished. To finish the rename later, stop the
service, `mv backend/jobtrack.sqlite backend/appstracker.sqlite`, and start it again.

## Notes / gotchas
- **Single worker only.** The systemd unit runs `uvicorn --workers 1` on purpose: the
  scheduler and Telegram poller are in-process singletons. More workers = double scrapes
  and Telegram `getUpdates` conflicts.
- **Backups.** The database is one file: `backend/appstracker.sqlite`. `cp` it (or
  `sqlite3 .backup`) on a cron for peace of mind.
- **Gmail token refresh.** `token.json` carries a long-lived refresh token; the app
  refreshes the short access token itself. If Google revokes it (password change, or the
  Testing-mode app idle > 6 months), re-run step 0b and re-copy the file.
- **First Gmail poll** just records the current mailbox state (no backfill); confirmations
  that arrive *after* that auto-flip the matching application to *confirmed*. Set
  `GMAIL_DRY_RUN=true` for a safe first run that only logs matches.
- **No public exposure.** If you ever want the dashboard reachable without a tunnel, put
  Caddy in front for automatic TLS — but that needs a domain and an open port, which the
  SSH-tunnel setup deliberately avoids.
