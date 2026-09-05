"""FastAPI application entry point.

A single always-on process: the REST API, the static Next.js dashboard (served from the
same origin when built), DB init, the background scheduler, and the Telegram long-poll
bot. Run with a single worker so the scheduler and bot aren't duplicated:
    uvicorn app.main:app --host 0.0.0.0 --port 8100 --workers 1
Local dev:
    uvicorn app.main:app --port 8100 --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router as api_router
from .config import settings
from .db import init_db
from .logutil import configure_logging
from .scheduler import shutdown_scheduler, start_scheduler
from .telegram.bot import start_polling, stop_polling

configure_logging()
log = logging.getLogger("appstracker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    start_polling()
    log.info("AppsTracker backend ready")
    yield
    stop_polling()
    shutdown_scheduler()


app = FastAPI(title="AppsTracker", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the built dashboard from the same origin (single-process deploy). Mounted last so
# the API routes above take precedence; falls back to API-only when not built yet.
_dist = settings.frontend_dist_path
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
    log.info("Serving dashboard from %s", _dist)
else:
    log.info("Frontend build not found at %s; running API-only", _dist)
