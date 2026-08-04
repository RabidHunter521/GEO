"""Authenticated, tenant-scoped API for the conversion-event evidence ledger.

Every response on this router is the admin shape (`ConversionEventOut`),
which includes admin-only fields (`metadata_json`, `calculation_method`,
`notes`) — see CLAUDE.md section 8. There is no client-facing route here; a
client-view summary surface must build its own explicit field whitelist
rather than reuse `ConversionEventOut`.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.conversion_event import (
    ConversionEventImportRequest,
    ConversionEventOut,
    ConversionImportResult,
    ConversionSummary,
)
from app.services import conversion_evidence_service
from app.services.conversion_evidence_service import (
    ConversionEventLocationNotFound,
    ConversionEventValidationError,
)


router = APIRouter(prefix="/clients/{client_id}/conversion-events", tags=["conversion-events"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post(
    "/import",
    response_model=ConversionImportResult,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def import_conversion_events(
    client_id: uuid.UUID, body: ConversionEventImportRequest, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    try:
        result = conversion_evidence_service.import_events(client_id, body.events, db)
    except ConversionEventLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    except ConversionEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get(
    "",
    response_model=list[ConversionEventOut],
    dependencies=[Depends(require_api_key)],
)
def list_conversion_events(
    client_id: uuid.UUID,
    evidence_level: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    events = conversion_evidence_service.list_events(
        client_id,
        db,
        evidence_level=evidence_level,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [ConversionEventOut.from_model(event) for event in events]


@router.get(
    "/summary",
    response_model=list[ConversionSummary],
    dependencies=[Depends(require_api_key)],
)
def summarize_conversion_events(
    client_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    return conversion_evidence_service.summarize_events(
        client_id, db, date_from=date_from, date_to=date_to
    )
