import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class ControlQuery(Base):
    """An admin-defined benchmark query SeenBy deliberately does NOT optimize.

    Run on every scan alongside the standard set (result rows carry
    is_control=True) but excluded from the GEO score and every analysis
    surface — it exists only to prove causation: optimized queries move,
    untouched ones don't. Deactivate (never delete) when the retainer starts
    touching a control's topic, so history stays intact.
    """

    __tablename__ = "control_queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="recommendation")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
