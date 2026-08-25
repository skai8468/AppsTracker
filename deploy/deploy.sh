#!/usr/bin/env bash
# Pull latest, rebuild, and restart JobTrack SG. Idempotent — safe to re-run.
# Usage (on the VM):  cd /opt/jobtrack-sg && ./deploy/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> git pull"
git pull --ff-only

echo "==> backend deps"
cd backend
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements.txt -q

echo "==> frontend static build (-> frontend/out)"
cd ../frontend
npm ci
# Cap Node heap so `next build` doesn't OOM on a 1 GB e2-micro (needs swap too — see
# DEPLOY.md). Empty API base => same-origin relative calls (served by the backend).
NODE_OPTIONS="--max-old-space-size=512" NEXT_PUBLIC_API_BASE="" npm run build

echo "==> restart service"
cd "$APP_DIR"
sudo systemctl restart jobtrack

echo "==> done. Logs: journalctl -u jobtrack -f"
