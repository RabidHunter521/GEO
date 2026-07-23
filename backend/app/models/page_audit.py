import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class PageAudit(Base):
    """One page-citability audit run for one URL.

    Re-auditing the same URL inserts a new row — per-URL history is the
    point ("was 45, now 78 after rewrite" is retainer proof; the Phase 5
    report reads it). Score is server-computed from the deterministic
    checks; Claude only ever contributes the rewrite suggestions. See
    docs/superpowers/specs/2026-07-11-page-citability-engine-design.md.
    """

    __tablename__ = "page_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # List of {"id","label","status","detail","points"} — points = earned.
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Claude items {"section","issue","rewrite"}, sanitized before persist.
    suggestions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # True when the Claude suggestions call failed — UI offers "Retry".
    suggestions_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
