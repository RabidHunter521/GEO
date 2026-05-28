import uuid
from datetime import datetime
from sqlalchemy import Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class GeoScore(Base):
    __tablename__ = "geo_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    ai_citability: Mapped[float] = mapped_column(Float, default=0.0)
    brand_authority: Mapped[float] = mapped_column(Float, default=0.0)
    content_quality: Mapped[float] = mapped_column(Float, default=0.0)
    technical_foundations: Mapped[float] = mapped_column(Float, default=0.0)
    structured_data: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
