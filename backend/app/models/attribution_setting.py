"""Per-client setup for lead-source attribution: the tracked WhatsApp link and
the inbound "how did you hear about us?" webhook.

One row per client, created lazily the first time an admin opens the setup.

- `click_token` is the public, unguessable path segment of the tracked
  WhatsApp link (`/wa/<click_token>`). It identifies the client and nothing
  else; it is not a credential to anything.
- `webhook_secret_hash` is the SHA-256 of the per-client webhook secret. The
  plaintext is shown to the admin exactly once, when generated, and never
  stored. Secrets are 256-bit random values, so looking a request up by the
  hash of the secret it presents is safe (same scheme as API tokens).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class AttributionSetting(Base):
    __tablename__ = "attribution_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    click_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Digits only, international format without "+" (e.g. "60123456789").
    # Optional: the website snippet keeps each button's own number, so this is
    # only needed for the bare tracked link (GBP, Instagram bio, QR codes).
    whatsapp_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    whatsapp_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracking_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    webhook_secret_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
