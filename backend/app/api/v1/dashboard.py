"""Global dashboard — admin-only reads (feed + summary tiles).

Thin routes: all logic in app/services/dashboard_service.py. Never mount or
reuse these from client_view — the cost figures must not be reachable from
any share-token surface (spec: admin-only by construction).
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import DASHBOARD_CATEGORY_LABELS
from app.core.database import get_db
from app.schemas.assessment import ReviewDueItem
from app.schemas.dashboard import DashboardFeedResponse, DashboardSummaryResponse
from app.services import dashboard_service
from app.services.dashboard_service import Period

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _period(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = None,
    end_date: date | None = None,
) -> Period:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be provided together",
        )
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=422, detail="end_date must be on or after start_date"
        )
    return dashboard_service.resolve_period(days, start_date, end_date)


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    dependencies=[Depends(require_api_key)],
)
def get_summary(
    period: Period = Depends(_period),
    client_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    return dashboard_service.get_summary(db, period, client_id=client_id)


@router.get(
    "/feed",
    response_model=DashboardFeedResponse,
    dependencies=[Depends(require_api_key)],
)
def get_feed(
    period: Period = Depends(_period),
    client_id: uuid.UUID | None = None,
    category: str | None = None,
    event_type: str | None = None,
    attention_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if category is not None and category not in DASHBOARD_CATEGORY_LABELS:
        raise HTTPException(status_code=422, detail="Unknown category")
    return dashboard_service.get_feed(
        db,
        period,
        client_id=client_id,
        category=category,
        event_type=event_type,
        attention_only=attention_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/assessment-reviews-due",
    response_model=list[ReviewDueItem],
    dependencies=[Depends(require_api_key)],
)
def assessment_reviews_due(db: Session = Depends(get_db)):
    """Active clients whose Brand Authority or Content Quality review is
    missing or older than ASSESSMENT_REVIEW_DAYS, oldest first."""
    from app.models.client import Client
    from app.services import assessment_service

    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None), Client.is_prospect.is_(False))
        .order_by(Client.name)
        .all()
    )
    items = [
        ReviewDueItem(
            client_id=c.id, client_name=c.name, dimension=d["dimension"],
            last_reviewed_at=d["last_reviewed_at"], due_reason=d["reason"],
        )
        for c in clients
        for d in assessment_service.review_due(c, db)
    ]
    # Never-reviewed first, then the longest-unreviewed.
    return sorted(items, key=lambda i: (i.last_reviewed_at is not None, i.last_reviewed_at or 0))
