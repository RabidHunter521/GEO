import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.constants import DEFAULT_SCAN_CADENCE_DAYS
from app.core.time import utcnow


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Hosted URL of the client's logo, shown in the read-only client view header.
    # Admin-entered (paste a URL) — no upload infra in MVP. NULL = text-only header.
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    brand_authority_score: Mapped[int] = mapped_column(Integer, default=0)
    brand_authority_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    content_quality_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_foundations_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    structured_data_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    score_drop_threshold: Mapped[int] = mapped_column(Integer, default=35)
    # AI-referral pipeline inputs (admin-set) — turn raw AI visitor counts into a
    # single revenue number on the report. avg_deal_value_rm NULL = RM line hidden.
    avg_deal_value_rm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visitor_to_lead_pct: Mapped[int] = mapped_column(
        Integer, default=2, server_default=text("2")
    )
    lead_to_customer_pct: Mapped[int] = mapped_column(
        Integer, default=20, server_default=text("20")
    )
    # Admin review cadence in days; drives the "next scan due" reminder. Reminder only.
    scan_cadence_days: Mapped[int] = mapped_column(
        Integer,
        default=DEFAULT_SCAN_CADENCE_DAYS,
        server_default=text(str(DEFAULT_SCAN_CADENCE_DAYS)),
    )
    # Platforms scanned for this client (subset of SCAN_PLATFORMS) — per-client cost control
    enabled_platforms: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["chatgpt", "perplexity", "gemini", "claude"],
        server_default=text("'[\"chatgpt\", \"perplexity\", \"gemini\", \"claude\"]'"),
    )
    # Read-only client view link. Plaintext by design: the admin must be able
    # to re-copy the link from settings at any time. NULL = no active link.
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    share_token_created_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Free-text admin notes (CRM-style). Admin-only — never exposed in client view.
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Prospect = a not-yet-paying lead scanned for cold outreach. Kept out of
    # the portfolio dashboard; flip to False ("Convert to Client") once signed.
    is_prospect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
