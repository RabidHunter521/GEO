"""Normalizes already-fetched Google Search Console rows into the tenant-
scoped `search_query_signals` table (Phase 5 Task 5 — see
docs/superpowers/plans/2026-07-29-seenby-measurement-business-proof.md).

This module does NOT talk to Google's API. It has no OAuth client, no token
storage, and no HTTP calls out — it receives data the caller already fetched
(via `SearchQuerySignalCreate`) and turns it into durable, deduplicated daily
signals a client can be evidence-correlated against later (e.g. tracked-query
visibility, conversion events). Credentials for the real Search Console
integration, whenever it exists, belong entirely outside this module.

`upsert_signals` is idempotent: syncing the same (client, property_uri,
signal_date, query, page, country, device) tuple twice updates the existing
row's metrics in place rather than creating a duplicate — the same tuple is
also the DB's unique constraint (`uq_search_query_signals_identity`), so a
concurrent double-sync still can't create a duplicate row even though this
function's own pre-check is not race-proof by itself.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.business_location import BusinessLocation
from app.models.search_query_signal import SearchQuerySignal
from app.schemas.search_query_signal import SearchQuerySignalCreate


class SearchConsoleLocationNotFound(ValueError):
    """Raised when a location is absent or belongs to a different client."""


class SearchConsoleSyncConflict(ValueError):
    """Raised when a concurrent sync collides with this one on the unique key."""


@dataclass(frozen=True)
class UpsertResult:
    inserted: int
    updated: int
    skipped: int
    total: int


@dataclass(frozen=True)
class SyncStatus:
    property_uris: list[str]
    total_signals: int
    earliest_signal_date: date | None
    latest_signal_date: date | None
    last_synced_at: datetime | None


def upsert_signals(
    client_id: uuid.UUID, signals: list[SearchQuerySignalCreate], db: Session
) -> UpsertResult:
    """Idempotent bulk upsert keyed on the table's unique identity tuple.

    Rows that already exist (same client, property_uri, signal_date, query,
    page, country, device) have their metrics overwritten and `synced_at`
    refreshed. Duplicate keys WITHIN the same call are counted as `skipped`
    (first occurrence wins) rather than silently overwritten twice.
    """
    if not signals:
        return UpsertResult(inserted=0, updated=0, skipped=0, total=0)

    _validate_locations(client_id, signals, db)

    property_uris = {s.property_uri for s in signals}
    dates = {s.signal_date for s in signals}
    existing_rows = (
        db.query(SearchQuerySignal)
        .filter(
            SearchQuerySignal.client_id == client_id,
            SearchQuerySignal.property_uri.in_(property_uris),
            SearchQuerySignal.signal_date.in_(dates),
        )
        .all()
    )
    existing_by_key = {_identity_key(row): row for row in existing_rows}

    inserted = updated = skipped = 0
    seen_keys: set[tuple] = set()
    for signal in signals:
        key = (
            signal.property_uri,
            signal.signal_date,
            signal.query,
            signal.page,
            signal.country,
            signal.device,
        )
        if key in seen_keys:
            skipped += 1
            continue
        seen_keys.add(key)

        existing = existing_by_key.get(key)
        if existing is not None:
            existing.location_id = signal.location_id
            existing.clicks = signal.clicks
            existing.impressions = signal.impressions
            existing.ctr = signal.ctr
            existing.position = signal.position
            existing.synced_at = utcnow()
            updated += 1
        else:
            row = SearchQuerySignal(
                client_id=client_id,
                location_id=signal.location_id,
                property_uri=signal.property_uri,
                signal_date=signal.signal_date,
                query=signal.query,
                page=signal.page,
                country=signal.country,
                device=signal.device,
                clicks=signal.clicks,
                impressions=signal.impressions,
                ctr=signal.ctr,
                position=signal.position,
            )
            db.add(row)
            existing_by_key[key] = row
            inserted += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SearchConsoleSyncConflict(
            "A concurrent sync already wrote one of these signals"
        ) from exc

    return UpsertResult(inserted=inserted, updated=updated, skipped=skipped, total=len(signals))


def get_sync_status(client_id: uuid.UUID, db: Session) -> SyncStatus:
    total, earliest, latest, last_synced = (
        db.query(
            func.count(SearchQuerySignal.id),
            func.min(SearchQuerySignal.signal_date),
            func.max(SearchQuerySignal.signal_date),
            func.max(SearchQuerySignal.synced_at),
        )
        .filter(SearchQuerySignal.client_id == client_id)
        .one()
    )
    property_uris = sorted(
        uri
        for (uri,) in db.query(SearchQuerySignal.property_uri)
        .filter(SearchQuerySignal.client_id == client_id)
        .distinct()
        .all()
    )
    return SyncStatus(
        property_uris=property_uris,
        total_signals=total or 0,
        earliest_signal_date=earliest,
        latest_signal_date=latest,
        last_synced_at=last_synced,
    )


def list_signals(
    client_id: uuid.UUID,
    db: Session,
    *,
    query_filter: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SearchQuerySignal]:
    query = db.query(SearchQuerySignal).filter(SearchQuerySignal.client_id == client_id)
    if query_filter:
        query = query.filter(SearchQuerySignal.query.ilike(f"%{query_filter}%"))
    if date_from is not None:
        query = query.filter(SearchQuerySignal.signal_date >= date_from)
    if date_to is not None:
        query = query.filter(SearchQuerySignal.signal_date <= date_to)
    return (
        query.order_by(SearchQuerySignal.signal_date.desc(), SearchQuerySignal.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def _identity_key(row: SearchQuerySignal) -> tuple:
    return (row.property_uri, row.signal_date, row.query, row.page, row.country, row.device)


def _validate_locations(
    client_id: uuid.UUID, signals: list[SearchQuerySignalCreate], db: Session
) -> None:
    location_ids = {s.location_id for s in signals if s.location_id is not None}
    if not location_ids:
        return
    owned_ids = {
        location_id
        for (location_id,) in db.query(BusinessLocation.id)
        .filter(
            BusinessLocation.client_id == client_id,
            BusinessLocation.id.in_(location_ids),
        )
        .all()
    }
    missing = location_ids - owned_ids
    if missing:
        raise SearchConsoleLocationNotFound("Location not found for this client")
