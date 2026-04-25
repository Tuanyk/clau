"""Google Search Console API. Auth: same SA as GA4."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()

_service = None
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _get_service():
    global _service
    if _service is not None:
        return _service
    if not settings()["google_sa"].configured:
        raise HTTPException(503, "gsc not configured (no service account JSON)")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings()["google_sa"].credentials_path, scopes=SCOPES
    )
    _service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    return _service


@router.get("/sites")
async def sites() -> dict:
    def _do():
        svc = _get_service()
        resp = svc.sites().list().execute()
        return {"sites": resp.get("siteEntry", [])}

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gsc error: {e}") from e


class SearchAnalyticsRequest(BaseModel):
    site_url: str
    start_date: str
    end_date: str
    dimensions: list[str] = Field(default_factory=lambda: ["query"])
    row_limit: int = 1000
    start_row: int = 0
    type: str | None = None
    dimension_filter_groups: list[dict[str, Any]] | None = None
    aggregation_type: str | None = None


@router.post("/search-analytics")
async def search_analytics(req: SearchAnalyticsRequest) -> dict:
    def _do():
        svc = _get_service()
        body: dict[str, Any] = {
            "startDate": req.start_date,
            "endDate": req.end_date,
            "dimensions": req.dimensions,
            "rowLimit": req.row_limit,
            "startRow": req.start_row,
        }
        if req.type:
            body["type"] = req.type
        if req.dimension_filter_groups:
            body["dimensionFilterGroups"] = req.dimension_filter_groups
        if req.aggregation_type:
            body["aggregationType"] = req.aggregation_type
        resp = svc.searchanalytics().query(siteUrl=req.site_url, body=body).execute()
        return resp

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gsc error: {e}") from e
