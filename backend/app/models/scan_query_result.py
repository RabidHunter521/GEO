import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Index, String, Boolean, Integer, Text, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base
from app.core.time import utcnow


class ScanQueryResult(Base):
    __tablename__ = "scan_query_results"
    __table_args__ = (
        CheckConstraint("sample_index > 0", name="ck_scan_query_results_sample_index_positive"),
        Index("ix_scan_query_results_tracked_query_observed", "tracked_query_id", "observed_at"),
        Index(
            "ix_scan_query_results_scan_tracked_sample",
            "scan_id",
            "tracked_query_id",
            "sample_index",
        ),
    )

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

    # Phase 5 (Measurement and Business Proof): links this observation back to
    # its governed TrackedQuery so repeated samples can be grouped for
    # stability analysis. SET NULL (not CASCADE) — a deleted/archived tracked
    # query must not erase the historical scan rows it produced; query_text
    # above already retains the original wording for audit independent of
    # this link.
    tracked_query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_queries.id", ondelete="SET NULL"), nullable=True
    )
    # 1-based position of this observation among the repeated samples taken
    # for the same tracked query within a scan (see query_sampling_service,
    # Task 3). Legacy pre-Phase-5 rows backfill to 1 (a single observation).
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Identifies which prompt template produced query_text, so a stability
    # comparison never mixes answers gathered under different wording.
    prompt_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="v1", server_default="v1"
    )
    # The underlying AI model that produced response_text (e.g. "gpt-4o"),
    # distinct from `platform` above which is the product/vendor surface
    # (chatgpt, perplexity, gemini, claude). Legacy rows backfill to
    # "unknown" since the exact model version was not recorded pre-Phase-5.
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown", server_default="unknown"
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # When the sample was actually taken. Distinct from created_at (DB insert
    # time): for legacy rows the two coincide; going forward a scan may batch
    # several samples whose real observation times differ from insert time.
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=text("now()")
    )

    tracked_query: Mapped["TrackedQuery | None"] = relationship(  # noqa: F821 — ruff false-positive on SQLAlchemy string forward-ref
        "TrackedQuery",
        back_populates="scan_query_results",
    )

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
