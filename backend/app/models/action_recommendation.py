import uuid
from datetime import datetime
from sqlalchemy import Float, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ActionRecommendation(Base):
    __tablename__ = "action_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    geo_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geo_scores.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_text: Mapped[str] = mapped_column(Text, nullable=False)
    # one of: ai_citability | brand_authority | content_quality | technical_foundations | structured_data
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    estimated_impact: Mapped[float] = mapped_column(Float, default=0.0)
    # high | medium | low — derived from estimated_impact
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    # open | done | dismissed | superseded
    status: Mapped[str] = mapped_column(String(20), default="open")
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
