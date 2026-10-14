import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    CUSTOM_QUESTION_MAX_LENGTH,
    CUSTOM_QUESTION_MIN_LENGTH,
    MAX_CUSTOM_QUESTIONS,
    BRAND_ALIAS_MAX_LENGTH,
    BRAND_ALIAS_MIN_LENGTH,
    MAX_BRAND_ALIASES,
    SCAN_PLATFORMS,
    SCORED_PLATFORMS,
    DEFAULT_SCAN_CADENCE_DAYS,
    INDUSTRY_PACK_KEYS,
    SHARE_LINK_EXPIRY_DAYS_OPTIONS,
)

# Lightweight email check — full RFC validation needs the email-validator
# package, which we deliberately avoid adding for an admin-entered field.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def clean_brand_aliases(value: list[str] | None) -> list[str] | None:
    """Trim, collapse whitespace and de-duplicate (case-insensitively) a list of
    brand aliases, rejecting ones too short to match safely. Shared by the
    client and competitor schemas."""
    if value is None:
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        alias = " ".join(str(raw).split())
        if not alias:
            continue
        if len(alias) < BRAND_ALIAS_MIN_LENGTH or len(alias) > BRAND_ALIAS_MAX_LENGTH:
            raise ValueError(
                f"Each alias must be {BRAND_ALIAS_MIN_LENGTH}-{BRAND_ALIAS_MAX_LENGTH} characters"
            )
        if alias.lower() in seen:
            continue
        seen.add(alias.lower())
        cleaned.append(alias)
    if len(cleaned) > MAX_BRAND_ALIASES:
        raise ValueError(f"At most {MAX_BRAND_ALIASES} aliases")
    return cleaned


class CustomQuestion(BaseModel):
    """One admin-written scan question. `category` decides how it counts:
    recommendation and local are discovery questions (they count toward AI
    Citability); brand and comparison are tracked but not scored."""

    text: str = Field(min_length=CUSTOM_QUESTION_MIN_LENGTH, max_length=CUSTOM_QUESTION_MAX_LENGTH)
    category: Literal["recommendation", "local", "brand", "comparison"] = "recommendation"

    @field_validator("text", mode="before")
    @classmethod
    def _collapse_whitespace(cls, value):
        return " ".join(str(value).split()) if value is not None else value


def clean_custom_questions(value: list[CustomQuestion] | None) -> list[CustomQuestion] | None:
    """De-duplicate (case-insensitively) and cap the list."""
    if value is None:
        return None
    seen: set[str] = set()
    cleaned: list[CustomQuestion] = []
    for question in value:
        key = question.text.casefold()
        if key in seen:
            continue
        seen.add(key)
        # Rebuilt so `category` counts as set even when it was defaulted: the
        # update route dumps with exclude_unset, which would otherwise store
        # the question without its category.
        cleaned.append(CustomQuestion(text=question.text, category=question.category))
    if len(cleaned) > MAX_CUSTOM_QUESTIONS:
        raise ValueError(f"At most {MAX_CUSTOM_QUESTIONS} custom questions")
    return cleaned


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # max_length mirrors the DB columns (String(255)); a longer value would pass
    # validation here and then fail at INSERT.
    website: str = Field(min_length=4, max_length=255)
    industry: str = Field(min_length=1, max_length=255)
    is_prospect: bool = False


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # Other names AI answers use for this brand; any of them counts as Seen by AI.
    brand_aliases: list[str] | None = None
    website: str | None = Field(default=None, min_length=4, max_length=255)
    industry: str | None = Field(default=None, min_length=1, max_length=255)
    # What buyers call this business; fills {industry} in scan questions.
    # A blank string clears it (back to `industry`).
    buyer_term: str | None = Field(default=None, max_length=120)
    # Admin-written scan questions; the whole list is replaced on save.
    custom_questions: list[CustomQuestion] | None = None
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

    @field_validator("custom_questions")
    @classmethod
    def validate_custom_questions(
        cls, value: list[CustomQuestion] | None
    ) -> list[CustomQuestion] | None:
        return clean_custom_questions(value)

    @field_validator("buyer_term")
    @classmethod
    def validate_buyer_term(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Collapse whitespace; a blank value is sent explicitly to clear the
        # field, so it becomes NULL (back to `industry`), never "".
        return " ".join(value.split()) or None

    @field_validator("brand_aliases")
    @classmethod
    def validate_brand_aliases(cls, value: list[str] | None) -> list[str] | None:
        # None means "not sent"; the route skips it. An empty list clears them.
        return clean_brand_aliases(value)

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
        if not any(p in SCORED_PLATFORMS for p in ordered):
            # The Google surfaces are reported, not scored: with only them on,
            # AI Citability would have nothing to measure.
            raise ValueError(
                "Enable at least one of ChatGPT, Perplexity, Gemini or Claude"
            )
        return ordered


class ClientResponse(BaseModel):
    id: uuid.UUID
    name: str
    brand_aliases: list[str] = []
    website: str
    industry: str
    buyer_term: str | None = None
    custom_questions: list[CustomQuestion] = []
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

    @field_validator("custom_questions", mode="before")
    @classmethod
    def _unflushed_questions_are_empty(cls, v):
        # A stub or not-yet-flushed row has no list here yet.
        return v if isinstance(v, list) else []

    @field_validator("brand_aliases", mode="before")
    @classmethod
    def _unflushed_aliases_are_empty(cls, v):
        # A stub or not-yet-flushed row has no list here yet.
        return v if isinstance(v, list) else []


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
