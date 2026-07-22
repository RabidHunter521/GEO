import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class SiteAudit(Base):
    """One persisted run of the 19-check site AI-readiness audit.

    Every run inserts a new row — history is the point (Phase 5's monthly
    report reads latest-vs-previous for its technical-delta section).
    Competitor audits are live-only and never write here. See
    docs/superpowers/specs/2026-07-11-site-ai-readiness-audit-v2-design.md.
    """

    __tablename__ = "site_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Full list of check dicts: {"id","label","status","detail","fix"}
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
