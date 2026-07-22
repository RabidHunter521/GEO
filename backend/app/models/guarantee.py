import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class Guarantee(Base):
    """A written commitment: lift `metric` from baseline to target by deadline.

    status: "active" | "met" | "missed" | "void" — terminal states only via
    explicit admin resolution (system suggests, admin gates; a client never
    learns "missed" from an automated flow). last_state stores the most recent
    DERIVED pace state ("on_track"/"at_risk"/"met"/"deadline_passed") so the
    post-scan check can alert on transitions only.
    The commercial remedy (e.g. free month) lives in the engagement letter,
    not in code — admin_note carries the paper trail.
    """

    __tablename__ = "guarantees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_citability")
    baseline_value: Mapped[int] = mapped_column(Integer, nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    last_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
