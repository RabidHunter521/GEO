import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


OUTCOME_ACTION_TYPES = (
    "content", "technical", "structured_data", "fact_correction",
    "accuracy_review", "authority", "local_presence",
    "competitor_response", "measurement",
)

OUTCOME_ACTION_STATUSES = (
    "detected", "recommended", "approved_internal", "in_progress",
    "waiting_client", "ready_to_publish", "published",
    "waiting_verification", "verified", "no_change",
    "superseded", "dismissed",
)


class OutcomeAction(Base):
    """A client-scoped action referencing, but not replacing, specialist records."""

    __tablename__ = "outcome_actions"
    __table_args__ = (
        Index(
            "uq_outcome_actions_client_source_ref", "client_id", "source_ref", unique=True,
            postgresql_where=text("source_ref IS NOT NULL"),
            sqlite_where=text("source_ref IS NOT NULL"),
        ),
        Index(
            "uq_outcome_actions_approval_token_hash", "approval_token_hash", unique=True,
            postgresql_where=text("approval_token_hash IS NOT NULL"),
            sqlite_where=text("approval_token_hash IS NOT NULL"),
        ),
        Index("ix_outcome_actions_client_status", "client_id", "status"),
        Index("ix_outcome_actions_due_date", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    work_log_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_log_entries.id", ondelete="SET NULL"), nullable=True
    )
    content_deliverable_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_deliverables.id", ondelete="SET NULL"), nullable=True
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="recommended", server_default="recommended"
    )
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    destination_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    client_safe_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    client_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
