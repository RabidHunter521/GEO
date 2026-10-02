import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, Integer, Text, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core.constants import DEFAULT_SCAN_CADENCE_DAYS, DEFAULT_WORKSPACE_ID, SCAN_PLATFORMS
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
    # Canonical business phone for NAP-consistency checks (spec §3). Admin-entered
    # in settings; compared digits-only against phones found on verified directory pages.
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
        default=lambda: list(SCAN_PLATFORMS),
        server_default=text(
            "'[\"chatgpt\", \"perplexity\", \"gemini\", \"claude\", "
            "\"google_aio\", \"google_ai_mode\"]'"
        ),
    )
    # Read-only client view link. Plaintext by design: the admin must be able
    # to re-copy the link from settings at any time. NULL = no active link.
    # Owning workspace. Every client is in DEFAULT_WORKSPACE_ID until
    # independent agencies get their own workspaces.
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        default=lambda: uuid.UUID(DEFAULT_WORKSPACE_ID),
    )
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    share_token_created_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Optional expiry for the view link. NULL = never expires. An expired link
    # returns the same uniform 404 as a revoked one.
    share_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # When the client last opened their view link, and how many separate visits
    # they have made (a visit = an open more than SHARE_VIEW_VISIT_GAP_MINUTES
    # after the previous one). Admin previews are not counted. Admin-only.
    share_last_viewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    share_view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # GA4 property for automated AI-referral traffic sync. NULL = manual mode.
    ga4_property_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Registered legal entity (e.g. "Klinik Acme Sdn. Bhd.") and SSM number.
    # Admin-only: used for invoicing/contracts and emitted in the client's
    # schema.json (legalName / identifier) to help AI models resolve the right
    # entity. Never exposed in the client view and never used in scan queries.
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Free-text admin notes (CRM-style). Admin-only — never exposed in client view.
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Prospect = a not-yet-paying lead scanned for cold outreach. Kept out of
    # the portfolio dashboard; flip to False ("Convert to Client") once signed.
    is_prospect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Industry intelligence pack (Phase 4). Only the SELECTION lives here —
    # every pack-specific business fact stays in the shared Truth Vault, so the
    # packs specialize one horizontal core instead of forking it. NULL = no pack
    # reviewed yet; such clients keep the legacy QUERY_TEMPLATES path.
    # Validated against INDUSTRY_PACK_KEYS in the schema layer, not a PG enum,
    # so adding a pack never needs a migration.
    industry_pack: Mapped[str | None] = mapped_column(String(32), nullable=True)
    industry_subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Server-stamped from the pack registry, never admin-entered: pack
    # definitions are code-versioned, and this records which version's queries
    # and risk rules produced a client's stored evidence.
    industry_pack_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Phase 6 benchmarks. Opting out removes this client from every cohort
    # aggregate, in both directions: they stop contributing to peer numbers and
    # they stop receiving a comparison. Default False (participating) because
    # cohorts are anonymous, suppressed below threshold, and never expose a
    # member; a client who still objects gets a one-flag exit.
    benchmark_opt_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Client win notifications ("ChatGPT now recommends you for ..."). Off by
    # default: the client only hears about wins once an admin switches this on,
    # and wins confirmed while it is off are recorded but never sent later.
    win_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
