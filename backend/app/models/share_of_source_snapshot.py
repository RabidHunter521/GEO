import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShareOfSourceSnapshot(Base):
    """One persisted Share-of-Source computation per completed scan.

    Written by provenance_service.compute_and_persist_snapshot right after
    enrich_scan_sources in scan_service's post-commit flow (best-effort,
    never blocks the scan). Enables a trend read (history endpoint) and
    flip detection that compute_share_of_source's live, recompute-on-read
    behavior can't provide alone. See
    docs/superpowers/specs/2026-07-10-share-of-source-trend-flip-detection-design.md.
    """

    __tablename__ = "share_of_source_snapshots"
    __table_args__ = (
        UniqueConstraint("scan_id", name="uq_share_of_source_snapshots_scan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_third_party_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_share_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    competitor_shares: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    acquisition_list: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
