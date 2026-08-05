"""Authenticated aggregate market intelligence (Phase 6 Task 8).

Internal in this release. These aggregates are privacy-safe by construction,
but "privacy-safe" and "ready to publish" are different bars — anything that
goes public goes through the Task 7 review workflow, not through this router.

Period defaulting is shared with the benchmark routes so an operator reading
both surfaces is never comparing different months without noticing.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.schemas.market_intelligence import (
    PackSignalCandidate,
    QueryDemandRow,
    SourceInfluenceRow,
)
from app.services import market_intelligence_service
from app.services.benchmark_period import default_benchmark_period

router = APIRouter(
    prefix="/market-intelligence",
    tags=["market-intelligence"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/source-influence", response_model=list[SourceInfluenceRow])
def get_source_influence(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    start, end = default_benchmark_period(period_start, period_end)
    return market_intelligence_service.source_influence(db, start, end)


@router.get("/query-demand", response_model=list[QueryDemandRow])
def get_query_demand(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    start, end = default_benchmark_period(period_start, period_end)
    return market_intelligence_service.query_demand(db, start, end)


@router.get("/pack-signals", response_model=list[PackSignalCandidate])
def get_pack_signals(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Candidate pack updates for a maintainer to review.

    Read-only by design. Applying one is a deliberate pack-version change made
    by a person; nothing here edits a prompt or a risk rule.
    """
    start, end = default_benchmark_period(period_start, period_end)
    return market_intelligence_service.export_pack_signals(db, start, end)
