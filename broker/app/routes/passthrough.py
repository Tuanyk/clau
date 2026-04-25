"""Generic passthrough — escape hatch for endpoints not yet wrapped.

Currently only Meta Graph API: Claude can call any /<version>/<path> on
graph.facebook.com without ever seeing the access token.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings

router = APIRouter()


@router.api_route(
    "/meta/{path:path}",
    methods=["GET", "POST", "DELETE"],
)
async def meta_passthrough(path: str, request: Request) -> Response:
    cfg = settings()["meta"]
    if not cfg.configured:
        raise HTTPException(503, "meta not configured")

    base = f"https://graph.facebook.com/{cfg.graph_version}"
    url = f"{base}/{path.lstrip('/')}"

    params = dict(request.query_params)
    params["access_token"] = cfg.access_token

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
