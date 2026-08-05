"""Authenticated, tenant-scoped admin API for cohort benchmark comparisons
(Phase 6 Task 4).

Returns the admin `BenchmarkComparison`, which carries the cohort key and exact
member counts. The client-facing route lives in `app/api/v1/client_view.py` and
builds `BenchmarkComparisonPublic` instead of reusing this response model —
same separation as business-impact, and for the same reason: a field added here
must not be able to reach a share link by inheritance.

There is no cohort filter parameter, by design. The cohort is derived from the
client's own attributes; a caller-chosen filter is how a differencing attack
starts.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.benchmark_comparison import BenchmarkComparison
from app.services import benchmark_comparison_service
from app.services.benchmark_period import default_benchmark_period

router = APIRouter(prefix="/clients/{client_id}/benchmarks", tags=["benchmarks"])


@router.get(
    "",
    response_model=list[BenchmarkComparison],
    dependencies=[Depends(require_api_key)],
)
def get_client_benchmarks(
    client_id: uuid.UUID,
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")

    start, end = default_benchmark_period(period_start, period_end)
    return benchmark_comparison_service.get_client_comparisons(db, client, start, end)
