"""Meta Graph API (Marketing API) endpoints.

Auth: access token injected from META_ACCESS_TOKEN. Claude never sees it.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()


def _client() -> httpx.AsyncClient:
    cfg = settings()["meta"]
    if not cfg.configured:
        raise HTTPException(503, "meta not configured (META_ACCESS_TOKEN missing)")
    base = f"https://graph.facebook.com/{cfg.graph_version}"
    return httpx.AsyncClient(base_url=base, timeout=30.0)


def _normalize_account(ad_account_id: str) -> str:
    aid = ad_account_id.strip()
    return aid if aid.startswith("act_") else f"act_{aid}"


async def _get_paginated(path: str, params: dict[str, Any], limit_pages: int) -> list[dict]:
    """Follow Graph API cursor pagination up to limit_pages."""
    out: list[dict] = []
    async with _client() as c:
        params = dict(params)
        params.setdefault("access_token", settings()["meta"].access_token)
        url: str | None = path
        for _ in range(limit_pages):
            if url is None:
                break
            r = await c.get(url, params=params if url == path else None)
            if r.status_code >= 400:
                raise HTTPException(r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
            payload = r.json()
            out.extend(payload.get("data", []))
            url = payload.get("paging", {}).get("next")
    return out


class InsightsRequest(BaseModel):
    ad_account_id: str
    fields: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    max_pages: int = 5


@router.post("/insights")
async def insights(req: InsightsRequest) -> dict:
    """Ad-account-level insights with optional breakdowns / level / date_preset.

    Common params: date_preset, time_range, level, breakdowns, filtering, limit.
    """
    aid = _normalize_account(req.ad_account_id)
    params = dict(req.params)
    params["fields"] = ",".join(req.fields)
    rows = await _get_paginated(f"/{aid}/insights", params, req.max_pages)
    return {"data": rows, "count": len(rows)}


class CampaignsRequest(BaseModel):
    ad_account_id: str
    fields: list[str] = Field(default_factory=lambda: ["id", "name", "status", "objective"])
    params: dict[str, Any] = Field(default_factory=dict)
    max_pages: int = 10


@router.post("/campaigns")
async def campaigns(req: CampaignsRequest) -> dict:
    aid = _normalize_account(req.ad_account_id)
    params = dict(req.params)
    params["fields"] = ",".join(req.fields)
    rows = await _get_paginated(f"/{aid}/campaigns", params, req.max_pages)
    return {"data": rows, "count": len(rows)}


@router.get("/ad-accounts")
async def ad_accounts() -> dict:
    """Ad accounts the token holder has access to."""
    rows = await _get_paginated(
        "/me/adaccounts",
        {"fields": "id,name,account_status,currency,timezone_name"},
        limit_pages=5,
    )
    return {"data": rows, "count": len(rows)}
