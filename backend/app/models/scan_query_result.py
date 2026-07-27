import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.core.time import utcnow


class ScanQueryResult(Base):
    __tablename__ = "scan_query_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    # AI platform that produced this result (see SCAN_PLATFORMS). Pre-multi-platform rows are "gemini".
    platform: Mapped[str] = mapped_column(String(50), nullable=False, server_default="gemini")
    # CASCADE (not SET NULL): deleting a competitor must remove its query rows,
    # not null competitor_id — a nulled row reads as the client's own query and
    # corrupts visibility metrics (edge case #38). NULL here only ever means a
    # genuine client-owned query row.
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    hallucination_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Brand's rank in list-style AI answers (recommendation/local categories). Null when not ranked.
    recommendation_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Benchmark row from a ControlQuery — excluded from score and all analysis
    # surfaces; exists only for the optimized-vs-untouched causal comparison.
    is_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    sources: Mapped[list["ScanQuerySource"]] = relationship(  # noqa: F821 — ruff false-positive on SQLAlchemy string forward-ref
        "ScanQuerySource",
        back_populates="scan_query_result",
        cascade="all, delete-orphan",
    )
    # Compliance findings quoting this response. Deleting the row takes its
    # findings with it (the DB FK does the same); the 90-day purge only NULLs
    # response_text, so a finding's copied quote still outlives the raw text.
    misinformation_findings: Mapped[list["MisinformationFinding"]] = relationship(  # noqa: F821 — ruff false-positive on SQLAlchemy string forward-ref
        "MisinformationFinding",
        cascade="all, delete-orphan",
    )
