import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class PlacementTarget(Base):
    """A third-party page AI answers draw on for the client's buyer questions
    that does not name the client — a placement to win.

    One row per (client, canonical URL), refreshed after every scan by
    placement_service.refresh_targets and kept across scans (stale, never
    deleted, so dismissals and history survive). Lifecycle:
    open -> pursuing (an Outcome Action exists) -> placed (the page now names
    the client) -> verified (the Outcome Action's question now sees the
    client). See docs/superpowers/plans/2026-10-02-placement-engine.md.

    Admin-only: contact details and outreach never reach a client surface.
    """

    __tablename__ = "placement_targets"
    __table_args__ = (
        UniqueConstraint("client_id", "url", name="uq_placement_targets_client_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # PLACEMENT_CATEGORIES
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # PLACEMENT_STATUSES
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")

    # Evidence accumulated across scans (answers that drew on the page while
    # the client was not seen on it).
    answers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    platforms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    query_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    competitors_present: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # The latest answer that drew on this page while the client was not Seen by
    # AI: the question whose flip proves a placement worked.
    representative_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_query_results.id", ondelete="SET NULL"), nullable=True
    )
    other_businesses_listed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    priority_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    authority_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authority_assets.id", ondelete="SET NULL"), nullable=True
    )
    outcome_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outcome_actions.id", ondelete="SET NULL"), nullable=True
    )

    page_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outreach_drafts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    first_seen_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Consecutive completed scans in which the page did not appear.
    scans_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
