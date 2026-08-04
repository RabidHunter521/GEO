"""Validated admin payloads for the conversion-event evidence ledger.

`evidence_level`, `event_type`, and `source` are constrained with `Literal`
at this API boundary (the model columns are plain varchars — see
`app/models/conversion_event.py`), matching the existing convention in
`app/schemas/tracked_query.py` rather than a Python `enum.Enum` class, which
this codebase does not otherwise use.

The evidence-level invariants (CLAUDE.md-adjacent, but specific to this
subsystem — see the Phase 5 Task 6 brief):

- `observed` requires both `external_event_id` and `occurred_at`. The DB
  check constraint enforces this too (belt-and-suspenders, same pattern as
  `TrackedQueryDuplicateError` backing the partial unique index) — the
  service raises a clear 422-shaped error before the DB ever has to.
- Only `estimated` events may carry a negative `value_minor` (refunds /
  downward adjustments to a modeled figure). Every other level is a
  non-negative amount.
- `currency` is restricted to a small allowlist, not free-text ISO 4217 —
  see `ALLOWED_CURRENCIES` in `app/services/conversion_evidence_service.py`.

`ConversionSummary` deliberately has NO single "total" field. Evidence
levels are never summed into one number — see CLAUDE.md's broader stance on
never collapsing distinct evidence into a single misleading figure, and the
Phase 5 Task 6 brief's "never claim causality from correlation alone."
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.conversion_event import ConversionEvent


EvidenceLevel = Literal["observed", "attributed", "assisted", "estimated"]
ConversionEventType = Literal["lead", "booking", "call", "purchase", "form_submit"]
ConversionEventSource = Literal["ga4", "crm", "call_tracking", "booking_platform", "manual"]


class ConversionEventCreate(BaseModel):
    event_type: ConversionEventType
    source: ConversionEventSource
    external_event_id: str | None = Field(default=None, max_length=255)
    evidence_level: EvidenceLevel
    occurred_at: datetime | None = None
    value_minor: int = Field(default=0)
    currency: str = Field(default="MYR", min_length=3, max_length=3)
    location_id: uuid.UUID | None = None
    source_url: str | None = None
    metadata_json: dict | list | None = None
    calculation_method: str | None = Field(default=None, max_length=64)
    calculation_version: str | None = Field(default=None, max_length=16)
    notes: str | None = None

    model_config = {"extra": "forbid"}


class ConversionEventImportRequest(BaseModel):
    events: list[ConversionEventCreate] = Field(min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}


class ConversionEventOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    location_id: uuid.UUID | None
    event_type: str
    source: str
    external_event_id: str | None
    evidence_level: str
    occurred_at: datetime | None
    value_minor: int
    currency: str
    source_url: str | None
    # Admin-only fields — deliberately included here (this schema backs the
    # admin API), but NEVER reused as-is for a client-facing surface. A
    # client-view response must whitelist fields explicitly rather than
    # extend or alias this model.
    metadata_json: dict | list | None
    calculation_method: str | None
    calculation_version: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, event: ConversionEvent) -> "ConversionEventOut":
        return cls(
            id=event.id,
            client_id=event.client_id,
            location_id=event.location_id,
            event_type=event.event_type,
            source=event.source,
            external_event_id=event.external_event_id,
            evidence_level=event.evidence_level,
            occurred_at=event.occurred_at,
            value_minor=event.value_minor,
            currency=event.currency,
            source_url=event.source_url,
            metadata_json=event.metadata_json,
            calculation_method=event.calculation_method,
            calculation_version=event.calculation_version,
            notes=event.notes,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


class ConversionImportResult(BaseModel):
    inserted: int
    updated: int
    total: int


class ConversionSummary(BaseModel):
    """One evidence-labeled snapshot for a single currency + time window.

    No combined "total" field by design — see module docstring. A caller
    that needs a headline number must pick a level explicitly and say so;
    this schema will not let that happen implicitly.
    """

    observed_value_minor: int
    attributed_value_minor: int
    assisted_value_minor: int
    estimated_value_minor: int
    currency: str
    event_count_by_level: dict[str, int]
    window_start: date | None
    window_end: date | None
