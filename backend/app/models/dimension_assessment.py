import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class DimensionAssessment(Base):
    """Claude-suggested, admin-reviewed score for a manual GEO dimension
    (brand_authority | content_quality).

    The accepted value also lives on the Client row (where compute_geo_score
    reads it); this table is canonical for the structured evidence bullets and
    the audit trail (suggested vs final, when reviewed). raw_narrative is
    ADMIN-ONLY and must never reach a client-facing schema.
    """
    __tablename__ = "dimension_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_score: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_bullets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="suggested")
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Review safeguards. The reviewer's name at the time (kept if the account
    # is later removed); the reason, required whenever the score or evidence
    # differs from the suggestion; and the evidence as the admin edited it
    # (None = the suggested bullets were accepted unchanged).
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_bullets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The points checklist behind the score (SCORE_VERSION v1.6.0+): one entry
    # per ASSESSMENT_RUBRICS criterion with key, label, max, basis, points
    # (suggested), final_points (None until reviewed, or the admin's override),
    # evidence (client-safe) and admin_hint (admin-only). None on rows written
    # before the checklist; those are flagged for re-review.
    criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)

    @property
    def shown_bullets(self) -> list:
        """The evidence a client sees once reviewed: edited, else suggested."""
        return list(self.final_bullets if self.final_bullets is not None else self.evidence_bullets)
