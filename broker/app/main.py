"""Broker entry point.

Holds long-lived API credentials so they never enter the Claude container.
Claude calls these endpoints over plain HTTP without auth; the broker injects
provider-side credentials and forwards to Meta / Google.

Logging: method, path, status, duration only. We never log request or
response bodies — they may contain PII or credential-equivalent data.
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from app.config import configured_providers
from app.routes import ga4, google_ads, gsc, meta, passthrough

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("broker")

app = FastAPI(title="clau-broker", docs_url="/docs", redoc_url=None)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.info(
        "%s %s -> %d (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/health")
def health():
    return {"ok": True, "providers": configured_providers()}


app.include_router(meta.router, prefix="/meta", tags=["meta"])
app.include_router(ga4.router, prefix="/ga4", tags=["ga4"])
app.include_router(gsc.router, prefix="/gsc", tags=["gsc"])
app.include_router(google_ads.router, prefix="/google-ads", tags=["google-ads"])
app.include_router(passthrough.router, prefix="/passthrough", tags=["passthrough"])
