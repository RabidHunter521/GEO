"""One raw lead-source signal: a tracked WhatsApp click or a "how did you hear
about us?" answer.

Every signal is stored, AI-sourced or not, so the admin can see the share
("9 of 40 WhatsApp chats came from AI"). Only signals with an AI match also
write a `ConversionEvent` at the `attributed` evidence level — that is what
reaches the evidence ladder and the client view. A signal with no AI match
never touches the conversion ledger.

`external_id` makes every write idempotent: the webhook's own submission ID,
or a server-generated ID for clicks and manual entries. `raw_value` (the
answer text or referrer host) and `visitor_hash` are admin-only.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base

ATTRIBUTION_CHANNELS = ("whatsapp_click", "heard_about_us")


class AttributionSignal(Base):
    __tablename__ = "attribution_signals"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "channel", "external_id", name="uq_attribution_signals_client_channel_external"
        ),
        Index(
            "ix_attribution_signals_client_occurred",
            "client_id",
            sql_text("occurred_at DESC"),
        ),
        Index(
            "ix_attribution_signals_visitor",
            "client_id",
            "visitor_hash",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Display label of the AI platform matched (e.g. "ChatGPT"); NULL = no AI match.
    ai_platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "referrer" | "utm" | "self_reported" — which rule produced ai_platform.
    match_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # "webhook" | "manual" | "tracked_link"
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    visitor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversion_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversion_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
