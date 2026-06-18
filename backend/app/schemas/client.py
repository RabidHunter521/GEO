import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.core.constants import SCAN_PLATFORMS, DEFAULT_SCAN_CADENCE_DAYS

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
    # max_length mirrors the DB column (String(255)), not the RFC 320 ceiling.
    contact_email: str | None = Field(default=None, pattern=_EMAIL_PATTERN, max_length=255)
    logo_url: str | None = Field(default=None, max_length=512)
    brand_authority_score: int | None = Field(default=None, ge=0, le=100)
    brand_authority_evidence: str | None = None
    content_quality_score: int | None = Field(default=None, ge=0, le=100)
    content_quality_evidence: str | None = None
    score_drop_threshold: int | None = Field(default=None, ge=1, le=100)
    scan_cadence_days: int | None = Field(default=None, ge=1, le=365)
    enabled_platforms: list[str] | None = None
    is_prospect: bool | None = None
    internal_notes: str | None = None

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
    enabled_platforms: list[str] = SCAN_PLATFORMS
    share_token: str | None = None
    share_token_created_at: datetime | None = None
    created_at: datetime
    archived_at: datetime | None = None
    is_prospect: bool = False
    internal_notes: str | None = None

    model_config = {"from_attributes": True}


class ShareTokenResponse(BaseModel):
    share_token: str
    share_token_created_at: datetime


class ClientListItem(ClientResponse):
    latest_overall_score: float | None = None
    last_scan_at: datetime | None = None
    previous_overall_score: float | None = None
    latest_scan_status: str | None = None
    latest_scan_triggered_at: datetime | None = None
    next_scan_due: datetime | None = None
    is_scan_overdue: bool = False

    model_config = {"from_attributes": False}
