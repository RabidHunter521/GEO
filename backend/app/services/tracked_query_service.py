"""Tenant-safe CRUD and deterministic priority scoring for tracked queries.

A TrackedQuery is the durable identity for a query the client wants tracked
across repeated scans (see `app/models/tracked_query.py`). This module owns:

- Text normalization + duplicate prevention ahead of the DB's partial unique
  indexes (`uq_tracked_query_brand`, `uq_tracked_query_location`).
- Client/location tenancy checks — a client can never read, patch, or
  archive another client's row, and a location must belong to the same
  client it is being attached to.
- The priority formula from the Phase 5 Task 2 brief:

    priority = demand_weight            * 0.35
             + buyer_stage_weight       * 0.20
             + risk_weight              * 0.20
             + recent_change_weight     * 0.15
             + business_value_weight    * 0.10

  `demand_weight` is a persisted column supplied directly by the caller.
  `buyer_stage_weight` / `risk_weight` are derived from the persisted
  `buyer_stage` / `risk_level` categorical columns via the fixed maps below.
  `recent_change_weight` / `business_value_weight` have no columns on the
  model — they are scoring-only inputs, folded into `priority_score` at
  create/patch time and then discarded; a caller who wants them to keep
  contributing after an unrelated patch must resupply them, since nothing
  persists them individually (only their combined effect, `priority_score`,
  survives). Omitted scoring inputs default to the neutral midpoint (0.5),
  mirroring `outcome_priority_service.NEUTRAL_INPUT_VALUE`.

`priority_reasons` is intentionally NOT persisted (no column for it) — it is
recomputed on every read from whatever the row currently holds, so it can
never describe a state the row has since moved past.
"""

import re
import unicodedata
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.tracked_query import TrackedQuery
from app.schemas.tracked_query import TrackedQueryCreate, TrackedQueryPatch


class TrackedQueryLocationNotFound(ValueError):
    """Raised when a location is absent or belongs to a different client."""


class TrackedQueryDuplicateError(ValueError):
    """Raised when a normalized text would collide within its scope."""


NEUTRAL_WEIGHT = 0.5

DEMAND_WEIGHT_SHARE = 0.35
BUYER_STAGE_WEIGHT_SHARE = 0.20
RISK_WEIGHT_SHARE = 0.20
RECENT_CHANGE_WEIGHT_SHARE = 0.15
BUSINESS_VALUE_WEIGHT_SHARE = 0.10

# None covers a query with no buyer_stage assigned yet — scored as neutral,
# not zero, so an unclassified query isn't penalized ahead of triage.
BUYER_STAGE_WEIGHTS: dict[str | None, float] = {
    None: NEUTRAL_WEIGHT,
    "awareness": 0.35,
    "consideration": 0.65,
    "decision": 1.0,
}

RISK_LEVEL_WEIGHTS: dict[str, float] = {
    "low": 0.15,
    "standard": 0.5,
    "elevated": 0.75,
    "critical": 1.0,
}


def normalize_query_text(text: str) -> str:
    """Unicode-NFC, whitespace-collapsed, lowercased form used for dedup."""
    nfc = unicodedata.normalize("NFC", text)
    collapsed = re.sub(r"\s+", " ", nfc).strip()
    return collapsed.lower()


def create_tracked_query(
    client_id: uuid.UUID, payload: TrackedQueryCreate, db: Session
) -> TrackedQuery:
    if payload.location_id is not None:
        _validate_location(client_id, payload.location_id, db)

    normalized_text = normalize_query_text(payload.text)
    _assert_not_duplicate(client_id, payload.location_id, normalized_text, db)

    tracked_query = TrackedQuery(
        client_id=client_id,
        location_id=payload.location_id,
        text=payload.text,
        normalized_text=normalized_text,
        source=payload.source,
        intent=payload.intent,
        buyer_stage=payload.buyer_stage,
        service_key=payload.service_key,
        risk_level=payload.risk_level,
        demand_weight=payload.demand_weight,
        priority_score=_priority_score(
            demand_weight=payload.demand_weight,
            buyer_stage=payload.buyer_stage,
            risk_level=payload.risk_level,
            recent_change_weight=payload.recent_change_weight,
            business_value_weight=payload.business_value_weight,
        ),
    )
    db.add(tracked_query)
    try:
        db.commit()
    except IntegrityError as exc:
        # Belt-and-suspenders against a concurrent insert racing the
        # pre-check above — the partial unique index is the real guard.
        db.rollback()
        raise TrackedQueryDuplicateError(
            "A tracked query with this text already exists in this scope"
        ) from exc
    db.refresh(tracked_query)
    return tracked_query


def get_tracked_query(
    client_id: uuid.UUID, tracked_query_id: uuid.UUID, db: Session
) -> TrackedQuery | None:
    return (
        db.query(TrackedQuery)
        .filter(TrackedQuery.client_id == client_id, TrackedQuery.id == tracked_query_id)
        .first()
    )


def list_tracked_queries(
    client_id: uuid.UUID,
    db: Session,
    *,
    active: bool = True,
    location_id: uuid.UUID | None = None,
    intent: str | None = None,
) -> list[TrackedQuery]:
    if location_id is not None:
        _validate_location(client_id, location_id, db)

    query = db.query(TrackedQuery).filter(
        TrackedQuery.client_id == client_id, TrackedQuery.is_active.is_(active)
    )
    if location_id is not None:
        query = query.filter(TrackedQuery.location_id == location_id)
    if intent is not None:
        query = query.filter(TrackedQuery.intent == intent)
    return query.order_by(
        TrackedQuery.priority_score.desc(),
        TrackedQuery.created_at.asc(),
        TrackedQuery.id.asc(),
    ).all()


def patch_tracked_query(
    tracked_query: TrackedQuery, payload: TrackedQueryPatch, db: Session
) -> TrackedQuery:
    updates = payload.model_dump(exclude_unset=True, exclude={"recent_change_weight", "business_value_weight"})

    if "location_id" in updates and updates["location_id"] is not None:
        _validate_location(tracked_query.client_id, updates["location_id"], db)

    # Re-check the dedup scope whenever EITHER half of it moves — text alone
    # (same location) or location alone (same text) can each produce a
    # collision with an existing row.
    if "text" in updates:
        new_normalized = normalize_query_text(updates["text"])
        updates["normalized_text"] = new_normalized
    else:
        new_normalized = tracked_query.normalized_text
    new_location_id = updates.get("location_id", tracked_query.location_id)

    if ("text" in updates or "location_id" in updates) and (
        new_normalized != tracked_query.normalized_text
        or new_location_id != tracked_query.location_id
    ):
        _assert_not_duplicate(
            tracked_query.client_id,
            new_location_id,
            new_normalized,
            db,
            exclude_id=tracked_query.id,
        )

    for field, value in updates.items():
        setattr(tracked_query, field, value)

    tracked_query.priority_score = _priority_score(
        demand_weight=tracked_query.demand_weight,
        buyer_stage=tracked_query.buyer_stage,
        risk_level=tracked_query.risk_level,
        recent_change_weight=payload.recent_change_weight,
        business_value_weight=payload.business_value_weight,
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise TrackedQueryDuplicateError(
            "A tracked query with this text already exists in this scope"
        ) from exc
    db.refresh(tracked_query)
    return tracked_query


def archive_tracked_query(tracked_query: TrackedQuery, db: Session) -> TrackedQuery:
    """Deactivate instead of deleting — history (and scan links) stay intact."""
    tracked_query.is_active = False
    db.commit()
    db.refresh(tracked_query)
    return tracked_query


def priority_reasons_for(tracked_query: TrackedQuery) -> list[str]:
    """Human-readable drivers, recomputed fresh from the row's current state.

    Only reasons about persisted fields (demand_weight, buyer_stage,
    risk_level) — recent_change_weight and business_value_weight are not
    stored, so they cannot be reasoned about after the fact.
    """
    buyer_stage_weight = BUYER_STAGE_WEIGHTS.get(tracked_query.buyer_stage, NEUTRAL_WEIGHT)
    risk_weight = RISK_LEVEL_WEIGHTS.get(tracked_query.risk_level, NEUTRAL_WEIGHT)

    drivers = (
        (
            DEMAND_WEIGHT_SHARE * tracked_query.demand_weight,
            "Strong demand",
            tracked_query.demand_weight,
        ),
        (
            BUYER_STAGE_WEIGHT_SHARE * buyer_stage_weight,
            "Decision-stage buyer intent",
            buyer_stage_weight if tracked_query.buyer_stage == "decision" else 0.0,
        ),
        (
            RISK_WEIGHT_SHARE * risk_weight,
            "Elevated accuracy risk",
            risk_weight if tracked_query.risk_level in ("elevated", "critical") else 0.0,
        ),
    )
    return [
        reason
        for _, reason, gate in sorted(drivers, key=lambda driver: driver[0], reverse=True)
        if gate >= 0.75
    ][:3]


def _priority_score(
    *,
    demand_weight: float,
    buyer_stage: str | None,
    risk_level: str,
    recent_change_weight: float | None,
    business_value_weight: float | None,
) -> float:
    buyer_stage_weight = BUYER_STAGE_WEIGHTS.get(buyer_stage, NEUTRAL_WEIGHT)
    risk_weight = RISK_LEVEL_WEIGHTS.get(risk_level, NEUTRAL_WEIGHT)
    recent_change = recent_change_weight if recent_change_weight is not None else NEUTRAL_WEIGHT
    business_value = business_value_weight if business_value_weight is not None else NEUTRAL_WEIGHT

    priority = (
        demand_weight * DEMAND_WEIGHT_SHARE
        + buyer_stage_weight * BUYER_STAGE_WEIGHT_SHARE
        + risk_weight * RISK_WEIGHT_SHARE
        + recent_change * RECENT_CHANGE_WEIGHT_SHARE
        + business_value * BUSINESS_VALUE_WEIGHT_SHARE
    )
    return round(priority * 100, 2)


def _validate_location(client_id: uuid.UUID, location_id: uuid.UUID, db: Session) -> None:
    location = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.id == location_id, BusinessLocation.client_id == client_id)
        .first()
    )
    if location is None:
        raise TrackedQueryLocationNotFound("Location not found for this client")


def _assert_not_duplicate(
    client_id: uuid.UUID,
    location_id: uuid.UUID | None,
    normalized_text: str,
    db: Session,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    query = db.query(TrackedQuery).filter(
        TrackedQuery.client_id == client_id,
        TrackedQuery.normalized_text == normalized_text,
    )
    if location_id is not None:
        query = query.filter(TrackedQuery.location_id == location_id)
    else:
        query = query.filter(TrackedQuery.location_id.is_(None))
    if exclude_id is not None:
        query = query.filter(TrackedQuery.id != exclude_id)
    if query.first() is not None:
        raise TrackedQueryDuplicateError(
            "A tracked query with this text already exists in this scope"
        )
