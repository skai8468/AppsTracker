#!/usr/bin/env bash
# Pull latest, rebuild, and restart AppsTracker. Idempotent — safe to re-run.
# Run on the VM as root:   sudo /opt/appstracker/deploy/deploy.sh
# Builds run as the unprivileged `appstracker` user (so file ownership stays correct);
# the service restart runs as root.
set -euo pipefail

APP_DIR=/opt/appstracker

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo $APP_DIR/deploy/deploy.sh" >&2
  exit 1
fi

as_app() { sudo -u appstracker bash -lc "$1"; }

echo "==> git pull"
as_app "git -C $APP_DIR pull --ff-only"

echo "==> backend deps"
as_app "cd $APP_DIR/backend && { [ -d .venv ] || python3 -m venv .venv; } && ./.venv/bin/pip install --upgrade pip -q && ./.venv/bin/pip install -q -r requirements.txt"

echo "==> frontend static build (-> frontend/out)"
# Cap Node heap so `next build` doesn't OOM on a 1 GB e2-micro (swap also required —
# see DEPLOY.md). Empty API base => same-origin relative calls (served by the backend).
as_app "cd $APP_DIR/frontend && npm ci && NODE_OPTIONS='--max-old-space-size=512' NEXT_PUBLIC_API_BASE='' npm run build"

echo "==> restart service"
systemctl restart appstracker

echo "==> done. Logs: journalctl -u appstracker -f"
