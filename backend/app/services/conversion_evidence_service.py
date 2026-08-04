"""Tenant-safe CRUD, idempotent import, and evidence-labeled aggregation for
conversion events.

This module owns the invariants described in `app/models/conversion_event.py`
and `app/schemas/conversion_event.py`:

- `observed` events require both `external_event_id` and `occurred_at` — the
  DB check constraint backs this up, but validation happens here first so a
  bad batch never reaches the DB.
- Only `estimated` events may carry a negative `value_minor`.
- `currency` is restricted to `ALLOWED_CURRENCIES` — a small allowlist, not
  free-text ISO 4217, since an unrecognized currency code silently corrupts
  any downstream summary that assumes it can trust the field.
- Import is idempotent by `(client_id, source, external_event_id)`: reimporting
  the same GA4/CRM export twice updates the existing row instead of creating
  a duplicate. Events with no `external_event_id` (manual entries) always
  insert fresh — there is nothing to dedupe them against.
- Summaries never sum across evidence levels into one number, and never sum
  across currencies — see `summarize_events`.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.conversion_event import ConversionEvent
from app.schemas.conversion_event import (
    ConversionEventCreate,
    ConversionImportResult,
    ConversionSummary,
)


class ConversionEventValidationError(ValueError):
    """Raised when an event violates an evidence-level, currency, or value invariant."""


class ConversionEventLocationNotFound(ValueError):
    """Raised when a location is absent or belongs to a different client."""


# Small deliberate allowlist rather than a full ISO 4217 table — these are
# the currencies SeenBy clients actually transact in. Extending it is a code
# change, not a migration, same reasoning as `TrackedQuery.source` /
# `.intent` being plain varchars instead of a DB enum.
ALLOWED_CURRENCIES = {"MYR", "USD", "SGD", "GBP", "EUR", "AUD"}

EVIDENCE_LEVELS = ("observed", "attributed", "assisted", "estimated")


def import_events(
    client_id: uuid.UUID, events: list[ConversionEventCreate], db: Session
) -> ConversionImportResult:
    """Idempotently upsert a batch of events.

    Validates every event in the batch before touching the session, so a
    single invalid row aborts the whole import rather than leaving it
    half-applied.
    """
    location_ids = {event.location_id for event in events if event.location_id is not None}
    for location_id in location_ids:
        _validate_location(client_id, location_id, db)
    for payload in events:
        _validate_event(payload)

    inserted = 0
    updated = 0
    for payload in events:
        existing = None
        if payload.external_event_id is not None:
            existing = (
                db.query(ConversionEvent)
                .filter(
                    ConversionEvent.client_id == client_id,
                    ConversionEvent.source == payload.source,
                    ConversionEvent.external_event_id == payload.external_event_id,
                )
                .first()
            )
        if existing is not None:
            _apply_payload(existing, payload)
            updated += 1
        else:
            event = ConversionEvent(client_id=client_id)
            _apply_payload(event, payload)
            db.add(event)
            inserted += 1

    try:
        db.commit()
    except IntegrityError as exc:
        # Belt-and-suspenders against a concurrent import racing the
        # pre-check above — the partial unique index is the real guard.
        db.rollback()
        raise ConversionEventValidationError(
            "A conversion event with this source and external_event_id "
            "already exists for this client"
        ) from exc

    return ConversionImportResult(inserted=inserted, updated=updated, total=inserted + updated)


def list_events(
    client_id: uuid.UUID,
    db: Session,
    *,
    evidence_level: str | None = None,
    event_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversionEvent]:
    query = db.query(ConversionEvent).filter(ConversionEvent.client_id == client_id)
    if evidence_level is not None:
        query = query.filter(ConversionEvent.evidence_level == evidence_level)
    if event_type is not None:
        query = query.filter(ConversionEvent.event_type == event_type)
    if date_from is not None:
        query = query.filter(ConversionEvent.occurred_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(ConversionEvent.occurred_at <= datetime.combine(date_to, time.max))
    return (
        query.order_by(
            ConversionEvent.occurred_at.desc(),
            ConversionEvent.created_at.desc(),
            ConversionEvent.id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


def summarize_events(
    client_id: uuid.UUID,
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ConversionSummary]:
    """Aggregate by evidence level, one `ConversionSummary` per currency.

    Events with multiple currencies are NEVER combined into one summary —
    each currency gets its own object so a caller can never accidentally
    add MYR cents to USD cents. When a date window is supplied, events with
    no `occurred_at` (estimated events describing a modeled window rather
    than a point in time) are excluded, since we cannot say whether they
    fall inside it.
    """
    query = db.query(ConversionEvent).filter(ConversionEvent.client_id == client_id)
    if date_from is not None:
        query = query.filter(ConversionEvent.occurred_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(ConversionEvent.occurred_at <= datetime.combine(date_to, time.max))

    by_currency: dict[str, list[ConversionEvent]] = defaultdict(list)
    for event in query.all():
        by_currency[event.currency].append(event)

    summaries: list[ConversionSummary] = []
    for currency in sorted(by_currency):
        totals = {level: 0 for level in EVIDENCE_LEVELS}
        counts = {level: 0 for level in EVIDENCE_LEVELS}
        for event in by_currency[currency]:
            totals[event.evidence_level] += event.value_minor
            counts[event.evidence_level] += 1
        summaries.append(
            ConversionSummary(
                observed_value_minor=totals["observed"],
                attributed_value_minor=totals["attributed"],
                assisted_value_minor=totals["assisted"],
                estimated_value_minor=totals["estimated"],
                currency=currency,
                event_count_by_level=counts,
                window_start=date_from,
                window_end=date_to,
            )
        )
    return summaries


def _apply_payload(event: ConversionEvent, payload: ConversionEventCreate) -> None:
    event.location_id = payload.location_id
    event.event_type = payload.event_type
    event.source = payload.source
    event.external_event_id = payload.external_event_id
    event.evidence_level = payload.evidence_level
    event.occurred_at = payload.occurred_at
    event.value_minor = payload.value_minor
    event.currency = payload.currency
    event.source_url = payload.source_url
    event.metadata_json = payload.metadata_json
    event.calculation_method = payload.calculation_method
    event.calculation_version = payload.calculation_version
    event.notes = payload.notes


def _validate_event(payload: ConversionEventCreate) -> None:
    if payload.currency not in ALLOWED_CURRENCIES:
        raise ConversionEventValidationError(
            f"Unsupported currency: {payload.currency!r}. "
            f"Allowed: {sorted(ALLOWED_CURRENCIES)}"
        )
    if payload.evidence_level == "observed" and (
        payload.external_event_id is None or payload.occurred_at is None
    ):
        raise ConversionEventValidationError(
            "observed events require both external_event_id and occurred_at"
        )
    if payload.value_minor < 0 and payload.evidence_level != "estimated":
        raise ConversionEventValidationError(
            "negative value_minor is only allowed for estimated events"
        )


def _validate_location(client_id: uuid.UUID, location_id: uuid.UUID, db: Session) -> None:
    location = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.id == location_id, BusinessLocation.client_id == client_id)
        .first()
    )
    if location is None:
        raise ConversionEventLocationNotFound("Location not found for this client")
