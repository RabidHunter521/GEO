import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.core.time import utcnow


class ScanQuerySource(Base):
    """A source a platform cited when answering a client-owned query.

    Structured, purge-proof (no raw response text) — survives the 90-day raw
    purge like brand_detected. Captured inline during the scan; source_type /
    fetch_status / present_brands are filled by the post-commit enrichment step.
    """

    __tablename__ = "scan_query_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_query_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_query_results.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    # client_owned | competitor_owned | third_party ; null until enriched
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # pending | ok | blocked | error
    fetch_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    # {"client": bool, "competitors": [competitor_id_str, ...]} ; null until enriched
    present_brands: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    scan_query_result = relationship("ScanQueryResult", back_populates="sources")
