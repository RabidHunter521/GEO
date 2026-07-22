import uuid
from datetime import datetime
from sqlalchemy import Float, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class ContentAnalysis(Base):
    """One row per analysis run. History kept per client_id over time (like geo_scores)."""

    __tablename__ = "content_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pending | running | completed | failed — the crawl + Claude analysis runs in a Celery task
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # [{topic, status: strong|weak|missing}]
    topics_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{entity, covered: bool}]
    entities_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{topic, title, rationale}] — content ideas generated for "missing" topics
    suggested_content_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # informational only — does NOT feed the GEO score
    entity_coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    # {word_count, h1_count, faq_count, blog_count, schema_present}
    content_metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_quality_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_at: Mapped[datetime] = mapped_column(default=utcnow)
