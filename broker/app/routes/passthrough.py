"""Generic passthrough — escape hatch for endpoints not yet wrapped.

Currently Meta Graph API: Claude can call Graph paths without ever seeing the
access token. `/meta/...` uses META_ACCESS_TOKEN; `/meta-page/...` uses
META_PAGE_ACCESS_TOKEN or a page token derived from META_USER_ACCESS_TOKEN.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings
from app.routes.meta import _resolve_page_access_token

router = APIRouter()


async def _forward_meta(path: str, request: Request, access_token: str) -> Response:
    cfg = settings()["meta"]
    base = f"https://graph.facebook.com/{cfg.graph_version}"
    url = f"{base}/{path.lstrip('/')}"

    params = dict(request.query_params)
    params["access_token"] = access_token

    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in {"content-type", "accept"}
    }

    async with httpx.AsyncClient(timeout=60.0) as c:
        upstream = await c.request(
            request.method,
            url,
            params=params,
            content=body or None,
            headers=headers,
        )

    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() in {"content-type", "cache-control"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@router.api_route(
    "/meta/{path:path}",
    methods=["GET", "POST"],
)
async def meta_passthrough(path: str, request: Request) -> Response:
    """Generic Graph passthrough using META_ACCESS_TOKEN."""
    cfg = settings()["meta"]
    if not cfg.access_token:
        raise HTTPException(503, "META_ACCESS_TOKEN missing for /passthrough/meta")
    return await _forward_meta(path, request, cfg.access_token)


@router.api_route(
    "/meta-page/{path:path}",
    methods=["GET", "POST"],
)
async def meta_page_passthrough(path: str, request: Request) -> Response:
    """Page Graph passthrough using broker-local page-token resolution."""
    page_id = path.strip("/").split("/", 1)[0] or None
    page_token, _ = await _resolve_page_access_token(page_id)
    return await _forward_meta(path, request, page_token)
