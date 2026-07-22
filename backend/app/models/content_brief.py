import uuid
from datetime import datetime
from sqlalchemy import String, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class ContentBrief(Base):
    """Claude-generated content brief for a query the client lost to competitors.

    One brief per scan query result — regeneration upserts in place.
    Admin-only surface; never exposed through the client view API.
    """
    __tablename__ = "content_briefs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_query_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_query_results.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    # Denormalized so briefs stay displayable without joining scan results
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    competitors_seen: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str] = mapped_column(Text, nullable=False)
    outline: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)
