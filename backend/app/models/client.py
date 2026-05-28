import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_authority_score: Mapped[int] = mapped_column(Integer, default=0)
    content_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    technical_foundations_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    structured_data_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    score_drop_threshold: Mapped[int] = mapped_column(Integer, default=35)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
