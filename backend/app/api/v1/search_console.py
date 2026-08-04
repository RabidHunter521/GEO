"""Authenticated, tenant-scoped Search Console signal import/query API.

This is an import/normalization layer, not an OAuth integration: `/sync`
accepts Search Console rows the caller already fetched by whatever means
(there is no Google API client anywhere in this module) and normalizes them
into `search_query_signals`. No access token, refresh token, or unbounded
raw Google payload is ever accepted or returned here.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.search_query_signal import (
    SearchConsoleSyncRequest,
    SearchConsoleSyncResult,
    SearchConsoleSyncStatus,
    SearchQuerySignalOut,
)
from app.services import search_console_service
from app.services.search_console_service import SearchConsoleLocationNotFound


router = APIRouter(prefix="/clients/{client_id}/search-console", tags=["search-console"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post(
    "/sync",
    response_model=SearchConsoleSyncResult,
    dependencies=[Depends(require_api_key)],
)
def sync_search_console_signals(
    client_id: uuid.UUID, body: SearchConsoleSyncRequest, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    try:
        result = search_console_service.upsert_signals(client_id, body.signals, db)
    except SearchConsoleLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    return SearchConsoleSyncResult(
        inserted=result.inserted,
        updated=result.updated,
        skipped=result.skipped,
        total=result.total,
    )


@router.get(
    "/status",
    response_model=SearchConsoleSyncStatus,
    dependencies=[Depends(require_api_key)],
)
def get_search_console_status(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    status = search_console_service.get_sync_status(client_id, db)
    return SearchConsoleSyncStatus(
        property_uris=status.property_uris,
        total_signals=status.total_signals,
        earliest_signal_date=status.earliest_signal_date,
        latest_signal_date=status.latest_signal_date,
        last_synced_at=status.last_synced_at,
    )


@router.get(
    "/signals",
    response_model=list[SearchQuerySignalOut],
    dependencies=[Depends(require_api_key)],
)
def list_search_console_signals(
    client_id: uuid.UUID,
    query: str | None = Query(default=None, max_length=2000),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    signals = search_console_service.list_signals(
        client_id,
        db,
        query_filter=query,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return signals
