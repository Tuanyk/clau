"""Broker entry point.

Holds long-lived API credentials so they never enter the Claude container.
Claude calls these endpoints over plain HTTP without auth; the broker injects
provider-side credentials and forwards to Meta / Google.

Per-request bodies are logged to a JSONL file and rendered at /dashboard so
the user can audit exactly what the agent is sending. See `request_log.py`.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import configured_providers
from app.request_log import LOG_FILE, render_dashboard, request_log_middleware
from app.routes import ga4, google_ads, gsc, gtm, meta, passthrough

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

app = FastAPI(title="clau-broker", docs_url="/docs", redoc_url=None)
app.middleware("http")(request_log_middleware)


@app.get("/health")
def health():
    return {
        "ok": True,
        "providers": configured_providers(),
        "log": str(LOG_FILE),
        "dashboard": "/dashboard",
    }


@app.get("/dashboard")
def dashboard():
    return render_dashboard()


app.include_router(meta.router, prefix="/meta", tags=["meta"])
app.include_router(ga4.router, prefix="/ga4", tags=["ga4"])
app.include_router(gsc.router, prefix="/gsc", tags=["gsc"])
app.include_router(gtm.router, prefix="/gtm", tags=["gtm"])
app.include_router(google_ads.router, prefix="/google-ads", tags=["google-ads"])
app.include_router(passthrough.router, prefix="/passthrough", tags=["passthrough"])
