import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    SCAN_PLATFORMS,
    DEFAULT_SCAN_CADENCE_DAYS,
    INDUSTRY_PACK_KEYS,
    SHARE_LINK_EXPIRY_DAYS_OPTIONS,
)

# Lightweight email check — full RFC validation needs the email-validator
# package, which we deliberately avoid adding for an admin-entered field.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # max_length mirrors the DB columns (String(255)); a longer value would pass
    # validation here and then fail at INSERT.
    website: str = Field(min_length=4, max_length=255)
    industry: str = Field(min_length=1, max_length=255)
    is_prospect: bool = False


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website: str | None = Field(default=None, min_length=4, max_length=255)
    industry: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    target_audience: str | None = None
    city: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    # max_length mirrors the DB column (String(255)), not the RFC 320 ceiling.
    contact_email: str | None = Field(default=None, pattern=_EMAIL_PATTERN, max_length=255)
    logo_url: str | None = Field(default=None, max_length=512)
    brand_authority_score: int | None = Field(default=None, ge=0, le=100)
    brand_authority_evidence: str | None = None
    content_quality_score: int | None = Field(default=None, ge=0, le=100)
    content_quality_evidence: str | None = None
    # 0 disables the alert (the crossing test `score < 0` can never fire), which
    # is what the settings help text ("Set to 0 to disable") promises.
    score_drop_threshold: int | None = Field(default=None, ge=0, le=100)
    scan_cadence_days: int | None = Field(default=None, ge=1, le=365)
    # AI-referral pipeline inputs. avg_deal_value_rm has no default (deal size is
    # client-specific); the report's RM line only renders once it's set.
    avg_deal_value_rm: int | None = Field(default=None, ge=0, le=100_000_000)
    visitor_to_lead_pct: int | None = Field(default=None, ge=0, le=100)
    lead_to_customer_pct: int | None = Field(default=None, ge=0, le=100)
    enabled_platforms: list[str] | None = None
    is_prospect: bool | None = None
    internal_notes: str | None = None
    legal_name: str | None = Field(default=None, max_length=255)
    # SSM formats: 12-digit new format, optionally with the old number in
    # brackets, e.g. "202301012345 (1501234-X)".
    registration_number: str | None = Field(
        default=None, max_length=64, pattern=r"^[0-9A-Za-z()\- ]*$"
    )
    # GA4 property id (digits) for AI-referral traffic sync; None = manual mode.
    ga4_property_id: str | None = Field(default=None, max_length=32)
    # Industry intelligence pack. `industry_pack_version` is deliberately ABSENT:
    # pack definitions are code-versioned, so the server stamps the version and an
    # admin can never type one.
    industry_pack: str | None = None
    industry_subcategory: str | None = Field(default=None, max_length=64)
    # Removes this client from cohort benchmark aggregates in both directions:
    # they stop contributing to peer numbers and stop receiving a comparison.
    # Forward-looking only — see app/services/benchmark_publication_service.py.
    benchmark_opt_out: bool | None = None
    # Email the client when a win is confirmed (win_notification_service).
    win_notifications_enabled: bool | None = None
    # Control field, NOT a column. Switching an already-chosen pack changes which
    # queries a client is scanned on and resets benchmark comparability, so the
    # route refuses an unconfirmed switch. The route must pop this before its
    # setattr loop (clients.py writes every parsed field to the row).
    confirm_pack_change: bool = False

    @field_validator("industry_pack")
    @classmethod
    def validate_industry_pack(cls, value: str | None) -> str | None:
        # None stays reachable — it means "no pack reviewed yet", the state every
        # pre-Phase-4 client is in.
        if value is None:
            return None
        if value not in INDUSTRY_PACK_KEYS:
            raise ValueError(
                f"Unknown industry pack: {value}. Supported: {', '.join(INDUSTRY_PACK_KEYS)}"
            )
        return value

    @field_validator("enabled_platforms")
    @classmethod
    def validate_enabled_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = [p for p in value if p not in SCAN_PLATFORMS]
        if unknown:
            raise ValueError(f"Unknown platforms: {', '.join(unknown)}")
        # canonical order, de-duplicated
        ordered = [p for p in SCAN_PLATFORMS if p in value]
        if not ordered:
            raise ValueError("At least one platform must be enabled")
        return ordered


class ClientResponse(BaseModel):
    id: uuid.UUID
    name: str
    website: str
    industry: str
    description: str | None = None
    target_audience: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    phone: str | None = None
    contact_email: str | None = None
    logo_url: str | None = None
    brand_authority_score: int
    brand_authority_evidence: str | None = None
    content_quality_score: int
    content_quality_evidence: str | None = None
    technical_foundations_verified: bool
    structured_data_verified: bool
    score_drop_threshold: int
    scan_cadence_days: int = DEFAULT_SCAN_CADENCE_DAYS
    avg_deal_value_rm: int | None = None
    visitor_to_lead_pct: int = 2
    lead_to_customer_pct: int = 20
    enabled_platforms: list[str] = SCAN_PLATFORMS
    share_token: str | None = None
    ga4_property_id: str | None = None
    share_token_created_at: datetime | None = None
    share_token_expires_at: datetime | None = None
    share_last_viewed_at: datetime | None = None
    share_view_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None
    is_prospect: bool = False
    internal_notes: str | None = None
    legal_name: str | None = None
    registration_number: str | None = None
    industry_pack: str | None = None
    industry_subcategory: str | None = None
    industry_pack_version: str | None = None
    benchmark_opt_out: bool = False
    win_notifications_enabled: bool = False

    model_config = {"from_attributes": True}

    @field_validator("share_view_count", mode="before")
    @classmethod
    def _unflushed_count_is_zero(cls, v):
        # A just-created, not-yet-flushed Client has no column default applied.
        return 0 if v is None else v

    @field_validator("win_notifications_enabled", mode="before")
    @classmethod
    def _unflushed_flag_is_false(cls, v):
        return False if v is None else v


class ShareTokenRequest(BaseModel):
    # One of SHARE_LINK_EXPIRY_DAYS_OPTIONS, or None for a link that never expires.
    expires_in_days: int | None = None

    @field_validator("expires_in_days")
    @classmethod
    def _allowed_expiry(cls, v):
        if v is not None and v not in SHARE_LINK_EXPIRY_DAYS_OPTIONS:
            raise ValueError(f"expires_in_days must be one of {SHARE_LINK_EXPIRY_DAYS_OPTIONS} or null")
        return v


class ShareTokenResponse(BaseModel):
    share_token: str
    share_token_created_at: datetime
    share_token_expires_at: datetime | None = None


class ClientListItem(ClientResponse):
    latest_overall_score: float | None = None
    last_scan_at: datetime | None = None
    previous_overall_score: float | None = None
    latest_scan_status: str | None = None
    latest_scan_triggered_at: datetime | None = None
    next_scan_due: datetime | None = None
    is_scan_overdue: bool = False

    model_config = {"from_attributes": False}
