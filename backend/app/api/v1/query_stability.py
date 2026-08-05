"""Authenticated, tenant-scoped admin API for per-query answer stability
(Phase 5 Task 8).

Returns `list[QueryStabilityResponse]` — one row per tracked query in the
client's portfolio, regardless of whether enough samples exist to classify it
yet (so the admin can see which queries have no data at all). There is no
client-facing route here; `app/api/v1/client_view.py` builds its own
`/query-stability` endpoint against the same schema (stability data is not
admin-only — it carries no raw AI responses, confidence scores, or char
offsets; the `score` field is a 0.0-1.0 agreement ratio safe to surface as
"consistency" language per CLAUDE.md §8).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.query_stability import QueryStabilityResponse
from app.services import query_stability_service


router = APIRouter(prefix="/clients/{client_id}/query-stability", tags=["query-stability"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get(
    "",
    response_model=list[QueryStabilityResponse],
    dependencies=[Depends(require_api_key)],
)
def get_query_stability(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    return query_stability_service.calculate_portfolio_stability(client_id, db)
