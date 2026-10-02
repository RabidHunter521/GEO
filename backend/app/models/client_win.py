import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class ClientWin(Base):
    """A confirmed client win: on one platform, for one buyer question, the
    client newly became recommended (kind="recommended") or Seen by AI
    (kind="seen"), and the new answer held across WIN_CONFIRMING_SCANS
    consecutive scans. See app/services/win_notification_service.py.

    Every confirmed win is recorded, whether or not the client is notified, so
    the row doubles as the dedupe ledger (WIN_RENOTIFY_DAYS) and as an admin
    record of proof points.
    """

    __tablename__ = "client_wins"
    __table_args__ = (
        Index("ix_client_wins_client_detected", "client_id", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # The scan that confirmed the win (the latest of the confirming scans).
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # WIN_KINDS
    # Best list position in the confirming scan, for kind="recommended".
    recommendation_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending  — recorded, delivery not attempted yet (or interrupted mid-send)
    # sent     — delivered on at least one channel (see `channels`)
    # not_sent — notifications off for this client, or no contact on file
    # failed   — every available channel raised
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Comma-separated channel names that delivered, e.g. "email".
    channels: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
