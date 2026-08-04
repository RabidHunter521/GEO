"""Authenticated, tenant-scoped CRUD for the governed tracked-query portfolio."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.tracked_query import TrackedQuery
from app.schemas.tracked_query import TrackedQueryCreate, TrackedQueryOut, TrackedQueryPatch
from app.services import tracked_query_service
from app.services.tracked_query_service import (
    TrackedQueryDuplicateError,
    TrackedQueryLocationNotFound,
)


router = APIRouter(prefix="/clients/{client_id}/tracked-queries", tags=["tracked-queries"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _get_tracked_query_or_404(
    client_id: uuid.UUID, tracked_query_id: uuid.UUID, db: Session
) -> TrackedQuery:
    tracked_query = tracked_query_service.get_tracked_query(client_id, tracked_query_id, db)
    if tracked_query is None:
        raise HTTPException(status_code=404, detail="Tracked query not found")
    return tracked_query


def _out(tracked_query: TrackedQuery) -> TrackedQueryOut:
    reasons = tracked_query_service.priority_reasons_for(tracked_query)
    return TrackedQueryOut.from_model(tracked_query, reasons)


@router.get(
    "",
    response_model=list[TrackedQueryOut],
    dependencies=[Depends(require_api_key)],
)
def list_tracked_queries(
    client_id: uuid.UUID,
    active: bool = Query(default=True),
    location_id: uuid.UUID | None = Query(default=None),
    intent: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    try:
        tracked_queries = tracked_query_service.list_tracked_queries(
            client_id, db, active=active, location_id=location_id, intent=intent
        )
    except TrackedQueryLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    return [_out(tracked_query) for tracked_query in tracked_queries]


@router.post(
    "",
    response_model=TrackedQueryOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_tracked_query(
    client_id: uuid.UUID, body: TrackedQueryCreate, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    try:
        tracked_query = tracked_query_service.create_tracked_query(client_id, body, db)
    except TrackedQueryLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    except TrackedQueryDuplicateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(tracked_query)


@router.patch(
    "/{tracked_query_id}",
    response_model=TrackedQueryOut,
    dependencies=[Depends(require_api_key)],
)
def patch_tracked_query(
    client_id: uuid.UUID,
    tracked_query_id: uuid.UUID,
    body: TrackedQueryPatch,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    tracked_query = _get_tracked_query_or_404(client_id, tracked_query_id, db)
    try:
        tracked_query = tracked_query_service.patch_tracked_query(tracked_query, body, db)
    except TrackedQueryLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    except TrackedQueryDuplicateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(tracked_query)


@router.post(
    "/{tracked_query_id}/archive",
    response_model=TrackedQueryOut,
    dependencies=[Depends(require_api_key)],
)
def archive_tracked_query(
    client_id: uuid.UUID, tracked_query_id: uuid.UUID, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    tracked_query = _get_tracked_query_or_404(client_id, tracked_query_id, db)
    tracked_query = tracked_query_service.archive_tracked_query(tracked_query, db)
    return _out(tracked_query)
