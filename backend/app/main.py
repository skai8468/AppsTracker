"""FastAPI application entry point.

Wires the REST API, the Telegram webhook, DB init, and the background scheduler. Run:
    uvicorn app.main:app --port 8100 --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .config import settings
from .db import init_db
from .scheduler import shutdown_scheduler, start_scheduler
from .telegram.webhook import router as telegram_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("jobtrack")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    log.info("JobTrack SG backend ready")
    yield
    shutdown_scheduler()


app = FastAPI(title="JobTrack SG", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(telegram_router)


@app.get("/health")
def health():
    return {"status": "ok"}
