import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class SearchQuerySignal(Base):
    """A normalized, tenant-scoped daily Google Search Console signal.

    This is NOT a raw mirror of Google's Search Analytics API response — it
    is the import/normalization layer (Phase 5 Task 5) that turns
    already-fetched GSC rows into a durable, per-client shape usable for
    evidence correlation (e.g. against `TrackedQuery` observations and,
    later, conversion events). The service that writes these rows
    (`app.services.search_console_service`) never talks to Google directly
    and never stores OAuth tokens — credentials live only in the existing
    config mechanism, never on this model.

    `location_id` lets a multi-location client attribute signals to a
    specific `BusinessLocation` when its Search Console property is
    location-scoped; it is nullable because many clients run one property
    for the whole brand. Unlike `TrackedQuery.location_id`, this FK is not
    part of a composite (location_id, client_id) constraint — ownership is
    instead checked in the service layer
    (`search_console_service._validate_location`), mirroring
    `tracked_query_service._validate_location`.

    `country` mirrors Google's ISO 3166-1 alpha-3 country codes (e.g.
    "usa", "gbr"); "ZZZ" is the sentinel this codebase uses for "unknown /
    not broken out by country", not a real Google value. `device` mirrors
    Google's own enum values (DESKTOP / MOBILE / TABLET); "UNKNOWN" is this
    codebase's sentinel for rows that don't carry a device breakdown.

    The unique constraint mirrors the natural key of one Search Console
    performance row: a client can sync the same (query, page, date,
    country, device) combination for the same property any number of times
    and `upsert_signals` will update the existing row in place rather than
    duplicating it — this is what makes repeated syncs of overlapping date
    ranges idempotent.
    """

    __tablename__ = "search_query_signals"
    __table_args__ = (
        Index(
            "uq_search_query_signals_identity",
            "client_id",
            "property_uri",
            "signal_date",
            "query",
            "page",
            "country",
            "device",
            unique=True,
        ),
        Index("ix_search_query_signals_client_date", "client_id", "signal_date"),
        Index("ix_search_query_signals_client_query_date", "client_id", "query", "signal_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    property_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_date: Mapped[date_] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(String(2000), nullable=False)
    page: Mapped[str] = mapped_column(String(2000), nullable=False)
    country: Mapped[str] = mapped_column(
        String(3), nullable=False, default="ZZZ", server_default="ZZZ"
    )
    device: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    impressions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )
