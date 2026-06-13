import uuid
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ContentRoadmap(Base):
    """One row per roadmap generation. History kept per client_id over time
    (like content_analyses). Built from competitor lost-query data."""

    __tablename__ = "content_roadmaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pending | running | completed | failed — the Claude generation runs in a Celery task
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # [{month: 1|2|3, theme, priority: high|medium|low, target_queries: [str],
    #   competitors_winning: [str], content_type, suggested_title, rationale}]
    roadmap_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # How many lost/open queries fed the plan — drives the empty-state message
    source_query_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
