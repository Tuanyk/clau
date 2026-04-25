"""GA4 Data API. Auth: GOOGLE_APPLICATION_CREDENTIALS service account."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings()["google_sa"].configured:
        raise HTTPException(503, "ga4 not configured (no service account JSON in /run/broker-secrets)")
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    _client = BetaAnalyticsDataClient()
    return _client


class RunReportRequest(BaseModel):
    property_id: str
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str]
    date_ranges: list[dict[str, str]] = Field(
        default_factory=lambda: [{"start_date": "7daysAgo", "end_date": "today"}]
    )
    limit: int | None = None
    offset: int | None = None
    order_bys: list[dict[str, Any]] | None = None
    dimension_filter: dict[str, Any] | None = None
    metric_filter: dict[str, Any] | None = None


def _run_report_sync(req: RunReportRequest) -> dict:
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Metric,
        RunReportRequest as APIRunReportRequest,
    )

    client = _get_client()
    api_req = APIRunReportRequest(
        property=f"properties/{req.property_id}",
        dimensions=[Dimension(name=d) for d in req.dimensions],
        metrics=[Metric(name=m) for m in req.metrics],
        date_ranges=[DateRange(**d) for d in req.date_ranges],
        limit=req.limit or 0,
        offset=req.offset or 0,
    )
    resp = client.run_report(api_req)
    rows = []
    for row in resp.rows:
        rows.append(
            {
                "dimensions": [v.value for v in row.dimension_values],
                "metrics": [v.value for v in row.metric_values],
            }
        )
    return {
        "dimension_headers": [h.name for h in resp.dimension_headers],
        "metric_headers": [{"name": h.name, "type": h.type_.name} for h in resp.metric_headers],
        "rows": rows,
        "row_count": resp.row_count,
    }


@router.post("/run-report")
async def run_report(req: RunReportRequest) -> dict:
    try:
        return await asyncio.to_thread(_run_report_sync, req)
    except HTTPException:
        raise
    except Exception as e:  # surface SDK errors as 502 with the message
        raise HTTPException(502, f"ga4 error: {e}") from e
