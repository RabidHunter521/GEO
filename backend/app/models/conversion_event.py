"""A single normalized business-outcome event (lead, booking, call, purchase…).

`ConversionEvent` is the durable record that Phase 5's business-proof surface
reads from: it normalizes heterogeneous sources (GA4 exports, CRM webhooks,
call-tracking platforms, booking systems, manual admin entry) into one
tenant-scoped shape, tagged with an explicit `evidence_level` so a client
report can never quietly collapse "we watched this happen" and "we modeled
this" into a single undifferentiated number.

Evidence levels (see `app/schemas/conversion_event.py` for the Literal type
and the invariants each level carries):

- `observed`   — a source system recorded this; requires `external_event_id`
                 AND `occurred_at` (enforced by the DB check constraint
                 below, not just the service layer).
- `attributed` — directly attributed to AI visibility, with a linking reason
                 (carried in `metadata_json`, admin-only).
- `assisted`   — AI visibility was one factor among several.
- `estimated`  — modeled/projected value; carries `calculation_method` +
                 `calculation_version` so the model that produced it is
                 always traceable. Estimated is also the only level allowed
                 a negative `value_minor` (adjustment/refund entries).

`source` + `external_event_id` are how idempotent re-import is possible: the
partial unique index below lets `conversion_evidence_service.import_events`
upsert instead of duplicate whenever the source system's own event ID is
known, while manual entries (no external ID) always insert fresh.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class ConversionEvent(Base):
    __tablename__ = "conversion_events"
    __table_args__ = (
        CheckConstraint(
            "value_minor >= 0 OR evidence_level = 'estimated'",
            name="ck_conversion_events_value_minor_non_negative_unless_estimated",
        ),
        CheckConstraint(
            "evidence_level != 'observed' "
            "OR (external_event_id IS NOT NULL AND occurred_at IS NOT NULL)",
            name="ck_conversion_events_observed_requires_source_and_time",
        ),
        # Partial unique index — dedup only applies when the source system
        # gave us its own event ID; manual entries (external_event_id NULL)
        # always insert fresh rather than colliding with each other. Same
        # postgresql_where + sqlite_where pattern as
        # tracked_queries.uq_tracked_query_brand, so the rule holds in the
        # SQLite test suite too, not just Postgres.
        Index(
            "uq_conversion_events_client_source_external_id",
            "client_id",
            "source",
            "external_event_id",
            unique=True,
            postgresql_where=sql_text("external_event_id IS NOT NULL"),
            sqlite_where=sql_text("external_event_id IS NOT NULL"),
        ),
        Index(
            "ix_conversion_events_client_occurred",
            "client_id",
            sql_text("occurred_at DESC"),
        ),
        Index(
            "ix_conversion_events_client_evidence_occurred",
            "client_id",
            "evidence_level",
            sql_text("occurred_at DESC"),
        ),
        Index(
            "ix_conversion_events_client_type_occurred",
            "client_id",
            "event_type",
            sql_text("occurred_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL, not CASCADE: deleting/reassigning a location must not erase
    # conversion history attached to it — the event still belongs to the
    # client regardless of which location it was tagged against.
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    # Nullable: an `estimated` event may describe a modeled/projected window
    # rather than a single point-in-time occurrence. `observed` events are
    # forced non-null by the check constraint above.
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    value_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MYR", server_default="MYR")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Admin-only: linking reasons, raw source payload fragments, anything not
    # meant for a client-facing summary. Never included in a client-view
    # response — callers must whitelist fields explicitly.
    metadata_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    calculation_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculation_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
