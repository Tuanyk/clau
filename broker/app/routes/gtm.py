"""Google Tag Manager API. Auth: same service account as GA4 / GSC."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter()

_service = None
SCOPES = [
    "https://www.googleapis.com/auth/tagmanager.readonly",
]


def _get_service():
    global _service
    if _service is not None:
        return _service
    if not settings()["google_sa"].configured:
        raise HTTPException(503, "gtm not configured (no service account JSON)")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings()["google_sa"].credentials_path, scopes=SCOPES
    )
    _service = build("tagmanager", "v2", credentials=creds, cache_discovery=False)
    return _service


@router.get("/accounts")
async def accounts() -> dict:
    def _do():
        svc = _get_service()
        return svc.accounts().list().execute()

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gtm error: {e}") from e


@router.get("/accounts/{account_id}/containers")
async def containers(account_id: str) -> dict:
    def _do():
        svc = _get_service()
        return svc.accounts().containers().list(parent=f"accounts/{account_id}").execute()

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gtm error: {e}") from e


@router.get("/accounts/{account_id}/containers/{container_id}/workspaces")
async def workspaces(account_id: str, container_id: str) -> dict:
    def _do():
        svc = _get_service()
        parent = f"accounts/{account_id}/containers/{container_id}"
        return svc.accounts().containers().workspaces().list(parent=parent).execute()

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gtm error: {e}") from e


@router.get("/workspaces/{account_id}/{container_id}/{workspace_id}/tags")
async def tags(account_id: str, container_id: str, workspace_id: str) -> dict:
    def _do():
        svc = _get_service()
        parent = (
            f"accounts/{account_id}/containers/{container_id}/workspaces/{workspace_id}"
        )
        return svc.accounts().containers().workspaces().tags().list(parent=parent).execute()

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"gtm error: {e}") from e
