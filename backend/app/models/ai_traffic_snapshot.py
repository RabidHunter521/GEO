import uuid
from datetime import date, datetime
from sqlalchemy import Date, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class AiTrafficSnapshot(Base):
    """Manually entered monthly AI-referral visitor counts. Informational only — does NOT feed the GEO score."""

    __tablename__ = "ai_traffic_snapshots"
    __table_args__ = (UniqueConstraint("client_id", "period", name="uq_ai_traffic_snapshots_client_period"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    # First day of the month this snapshot covers, e.g. 2026-06-01
    period: Mapped[date] = mapped_column(Date, nullable=False)
    ai_visitors: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
