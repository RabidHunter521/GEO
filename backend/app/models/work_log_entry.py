import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class WorkLogEntry(Base):
    """One client-safe record of work delivered.

    Born client-safe (unlike ActivityLog, whose notes use internal admin
    vocabulary and must never reach a client). Manual-first: auto-triggers
    write status="suggested" only; the admin reviews, edits, and publishes.
    ONLY status="published" is ever client-visible. See
    docs/superpowers/specs/2026-07-11-retainer-packaging-design.md.
    """

    __tablename__ = "work_log_entries"
    __table_args__ = (
        # Idempotent auto-suggestions: one row per (client, triggering event).
        # Manual entries (NULL source_ref) are unconstrained.
        Index(
            "uq_work_log_entries_client_source_ref", "client_id", "source_ref", unique=True,
            postgresql_where=text("source_ref IS NOT NULL"),
            sqlite_where=text("source_ref IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # technical | content | authority | visibility | correction
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # Client-safe text, sanitized at write time; admin-editable before publish.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # auto | manual
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto", server_default="auto")
    # "<event>:<entity id>" — dedupe key for auto suggestions. NULL for manual.
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # suggested | published | dismissed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="suggested", server_default="suggested"
    )
    # When the work happened (editable pre-publish) — drives report period filtering.
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
