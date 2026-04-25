"""Google Ads SDK endpoints. Auth: developer token + OAuth refresh token.

Ships read-only by default (search). Mutations are deliberately not
auto-exposed — wire them deliberately if/when needed.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

router = APIRouter()

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings()["google_ads"].configured:
        raise HTTPException(
            503,
            "google_ads not configured (need GOOGLE_ADS_DEVELOPER_TOKEN, "
            "GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN; "
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID for MCC)",
        )
    from google.ads.googleads.client import GoogleAdsClient

    cfg = settings()["google_ads"].sdk_config()
    _client = GoogleAdsClient.load_from_dict(cfg)
    return _client


def _row_to_dict(row) -> dict:
    """Convert a GoogleAdsRow proto-plus message to a JSON-friendly dict."""
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(type(row).pb(row), preserving_proto_field_name=True)


class QueryRequest(BaseModel):
    customer_id: str
    gaql_query: str
    page_size: int = 10000


@router.post("/query")
async def query(req: QueryRequest) -> dict:
    """Run a GAQL search. Returns all rows (auto-pages)."""

    def _do():
        client = _get_client()
        ga_service = client.get_service("GoogleAdsService")
        request = client.get_type("SearchGoogleAdsRequest")
        request.customer_id = req.customer_id.replace("-", "")
        request.query = req.gaql_query
        request.page_size = req.page_size
        try:
            response = ga_service.search(request=request)
        except Exception as e:
            from google.ads.googleads.errors import GoogleAdsException

            if isinstance(e, GoogleAdsException):
                detail = {
                    "request_id": e.request_id,
                    "errors": [
                        {
                            "message": err.message,
                            "code": (
                                err.error_code.WhichOneof("error_code") if err.error_code else None
                            ),
                        }
                        for err in e.failure.errors
                    ],
                }
                raise HTTPException(400, detail) from e
            raise

        rows = [_row_to_dict(row) for row in response]
        return {"data": rows, "count": len(rows)}

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"google_ads error: {e}") from e


@router.get("/customers")
async def list_accessible_customers() -> dict:
    """List MCC-accessible customer resource names."""

    def _do():
        client = _get_client()
        svc = client.get_service("CustomerService")
        resp = svc.list_accessible_customers()
        return {"resource_names": list(resp.resource_names)}

    try:
        return await asyncio.to_thread(_do)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"google_ads error: {e}") from e
