import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.time import utcnow


class RemediationItem(Base):
    """A tracked issue the SeenBy team is working to fix for a client, carrying a
    status lifecycle ("flagged" -> "in_progress" -> "corrected") that persists
    across scans.

    Two kinds (item_type):
      - "hallucination": an AI platform gave an inaccurate answer about the client
      - "content_gap":   a neutral-intent query a competitor was seen for and the
                         client was not (a question worth winning back)

    This closes the loop the client pays the retainer for: instead of only
    flagging "AI is wrong about you", it shows Flagged -> In progress -> Corrected,
    and proves a competitor-won query was later won back. The per-scan
    ScanQueryResult.hallucination_flagged boolean can't track this — it resets
    every scan and content gaps aren't stored at all.

    Client-safe by construction: only `label` (the question), `platform`, and
    `detail` (competitor names) are ever surfaced — never raw AI responses.
    """

    __tablename__ = "remediation_items"
    __table_args__ = (
        # One row per (client, kind, platform, question). Re-syncing a scan
        # updates the existing row rather than duplicating it.
        UniqueConstraint(
            "client_id", "item_type", "platform", "label",
            name="uq_remediation_dedupe",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # hallucination | content_gap (see REMEDIATION_TYPES)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Platform key (e.g. "chatgpt"). "" for kinds without a single platform.
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    # The question/query text this item is about (the dedupe key, with platform).
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # Free detail — for content_gap, the competitor names seen winning it.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # flagged | in_progress | corrected (see REMEDIATION_STATUSES)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="flagged", server_default="flagged")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
