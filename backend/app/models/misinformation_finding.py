import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class MisinformationFinding(Base):
    """One reviewed statement an AI platform made about the client that is wrong
    or creates advertising risk.

    Every finding carries `quote` — a verbatim substring of the source row's
    response_text, verified server-side by misinformation_service before the row
    is ever created. Claude proposes candidates; the substring check is what
    makes a fabricated finding impossible to store.

    The quote is COPIED here at creation on purpose: raw responses are purged
    after 90 days (CLAUDE.md §8) and the finding must outlive them.

    Nothing below status="confirmed" reaches any client surface — an unreviewed
    "AI is lying about you" claim would itself be misinformation. Framing
    everywhere is "flags for your review", never compliance certification. See
    docs/superpowers/specs/2026-07-19-misinformation-compliance-design.md.
    """

    __tablename__ = "misinformation_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_query_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_query_results.id", ondelete="CASCADE"), nullable=False
    )
    # Optional Truth Vault evidence for deterministic factual-conflict candidates.
    # No cascade is deliberate: fact history referenced by scan evidence is retained.
    truth_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("truth_facts.id"), nullable=True, index=True
    )
    truth_fact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("truth_fact_versions.id"), nullable=True, index=True
    )
    # Verbatim substring of the source response — the evidence, never paraphrased.
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    # wrong_service | factual_error | prohibited_claim | outdated_info
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # COMPLIANCE_RULES key when the category is prohibited_claim; NULL otherwise.
    rule_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # high | medium | low
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    # One admin-facing sentence explaining why this is a problem.
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    # suggested | confirmed | dismissed | corrected | candidate_fixed | verified_fixed
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="suggested", server_default="suggested"
    )
    detected_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Stamped when the admin confirms or dismisses — NULL means nobody has looked.
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
