"""Meta Graph API endpoints.

Auth: access tokens are injected from broker-local env vars. The AI container
never sees provider tokens.
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
        raise HTTPException(503, "meta not configured (set META_ACCESS_TOKEN, META_USER_ACCESS_TOKEN, or META_PAGE_ACCESS_TOKEN)")
    base = f"https://graph.facebook.com/{cfg.graph_version}"
    return httpx.AsyncClient(base_url=base, timeout=30.0)


def _raise_graph_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail: Any
    if response.headers.get("content-type", "").startswith("application/json"):
        detail = response.json()
    else:
        detail = response.text
    raise HTTPException(response.status_code, detail)


def _require_access_token(token: str | None, env_hint: str) -> str:
    if token:
        return token
    raise HTTPException(503, f"meta token missing ({env_hint})")


def _normalize_account(ad_account_id: str) -> str:
    aid = ad_account_id.strip()
    return aid if aid.startswith("act_") else f"act_{aid}"


def _normalize_page_id(page_id: str | None) -> str:
    pid = (page_id or settings()["meta"].page_id or "").strip()
    if not pid:
        raise HTTPException(400, "page_id required (or set META_PAGE_ID)")
    return pid


def _with_field(fields: str, required: str) -> str:
    parts = [field.strip() for field in fields.split(",") if field.strip()]
    if required not in parts:
        parts.append(required)
    return ",".join(parts)


def _hide_page_token(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    has_token = bool(out.pop("access_token", None))
    out["has_page_access_token"] = has_token
    return out


async def _get_json(path: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
    async with _client() as c:
        params = dict(params)
        params.setdefault("access_token", access_token)
        response = await c.get(path, params=params)
        _raise_graph_error(response)
        return response.json()


async def _get_paginated(
    path: str,
    params: dict[str, Any],
    limit_pages: int,
    access_token: str | None = None,
) -> list[dict]:
    """Follow Graph API cursor pagination up to limit_pages."""
    out: list[dict] = []
    token = _require_access_token(access_token or settings()["meta"].access_token, "META_ACCESS_TOKEN missing")
    async with _client() as c:
        params = dict(params)
        params.setdefault("access_token", token)
        url: str | None = path
        for _ in range(limit_pages):
            if url is None:
                break
            r = await c.get(url, params=params if url == path else None)
            _raise_graph_error(r)
            payload = r.json()
            out.extend(payload.get("data", []))
            url = payload.get("paging", {}).get("next")
    return out


async def _resolve_page_access_token(page_id: str | None) -> tuple[str, str]:
    """Return (page_token, page_id) without exposing the token to the caller."""
    cfg = settings()["meta"]
    pid = _normalize_page_id(page_id)
    if cfg.page_access_token:
        return cfg.page_access_token, pid

    user_token = _require_access_token(
        cfg.user_access_token,
        "set META_PAGE_ACCESS_TOKEN, or set META_USER_ACCESS_TOKEN to derive page tokens",
    )
    rows = await _get_paginated(
        "/me/accounts",
        {"fields": "id,name,access_token"},
        limit_pages=10,
        access_token=user_token,
    )
    for row in rows:
        if str(row.get("id")) == pid:
            page_token = row.get("access_token")
            if not page_token:
                raise HTTPException(502, f"Meta did not return an access_token for page {pid}")
            return page_token, pid
    raise HTTPException(404, f"page {pid} not found in /me/accounts for configured user token")


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


@router.get("/pages")
async def pages(fields: str = "id,name,category,tasks", max_pages: int = 10) -> dict:
    """Pages available to the configured user token; page tokens are not returned."""
    cfg = settings()["meta"]
    if cfg.user_access_token:
        rows = await _get_paginated(
            "/me/accounts",
            {"fields": _with_field(fields, "access_token")},
            max_pages,
            access_token=cfg.user_access_token,
        )
        safe_rows = [_hide_page_token(row) for row in rows]
        return {"data": safe_rows, "count": len(safe_rows)}

    if cfg.page_access_token and cfg.page_id:
        row = await _get_json(f"/{cfg.page_id}", {"fields": fields}, cfg.page_access_token)
        row["has_page_access_token"] = True
        return {"data": [row], "count": 1}

    raise HTTPException(503, "set META_USER_ACCESS_TOKEN or META_PAGE_ACCESS_TOKEN plus META_PAGE_ID")


@router.get("/pages/{page_id}")
async def page_info(
    page_id: str,
    fields: str = "id,name,username,link,category,fan_count,followers_count,picture",
) -> dict:
    """Page profile fields using a page token resolved inside the broker."""
    page_token, pid = await _resolve_page_access_token(page_id)
    return await _get_json(f"/{pid}", {"fields": fields}, page_token)


class PageInsightsRequest(BaseModel):
    page_id: str | None = None
    metrics: list[str]
    params: dict[str, Any] = Field(default_factory=dict)
    max_pages: int = 5


@router.post("/page-insights")
async def page_insights(req: PageInsightsRequest) -> dict:
    """Page insights using META_PAGE_ACCESS_TOKEN or a derived page token."""
    page_token, pid = await _resolve_page_access_token(req.page_id)
    params = dict(req.params)
    params["metric"] = ",".join(req.metrics)
    rows = await _get_paginated(f"/{pid}/insights", params, req.max_pages, page_token)
    return {"page_id": pid, "data": rows, "count": len(rows)}
