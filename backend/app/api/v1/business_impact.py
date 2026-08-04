"""Authenticated, tenant-scoped admin API for the business-impact evidence
ladder (Phase 5 Task 7).

Returns `ImpactSummary` — the full admin shape, one per currency. There is
no client-facing route here; `app/api/v1/client_view.py` builds its own
`/business-impact` endpoint against `ImpactSummaryPublic` instead of reusing
this response model.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.business_impact import ImpactSummary
from app.services import business_impact_service


router = APIRouter(prefix="/clients/{client_id}/business-impact", tags=["business-impact"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get(
    "",
    response_model=list[ImpactSummary],
    dependencies=[Depends(require_api_key)],
)
def get_business_impact(
    client_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    return business_impact_service.get_impact_summary(
        client_id, db, date_from=date_from, date_to=date_to
    )
