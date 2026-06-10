import uuid
from datetime import datetime
from pydantic import BaseModel, Field

# Lightweight email check — full RFC validation needs the email-validator
# package, which we deliberately avoid adding for an admin-entered field.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str = Field(min_length=4, max_length=500)
    industry: str = Field(min_length=1, max_length=255)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website: str | None = Field(default=None, min_length=4, max_length=500)
    industry: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    target_audience: str | None = None
    city: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, pattern=_EMAIL_PATTERN, max_length=320)
    brand_authority_score: int | None = Field(default=None, ge=0, le=100)
    brand_authority_evidence: str | None = None
    content_quality_score: int | None = Field(default=None, ge=0, le=100)
    content_quality_evidence: str | None = None
    score_drop_threshold: int | None = Field(default=None, ge=1, le=100)


class ClientResponse(BaseModel):
    id: uuid.UUID
    name: str
    website: str
    industry: str
    description: str | None = None
    target_audience: str | None = None
    city: str | None = None
    state: str | None = None
    contact_email: str | None = None
    brand_authority_score: int
    brand_authority_evidence: str | None = None
    content_quality_score: int
    content_quality_evidence: str | None = None
    technical_foundations_verified: bool
    structured_data_verified: bool
    score_drop_threshold: int
    created_at: datetime
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClientListItem(ClientResponse):
    latest_overall_score: float | None = None
    last_scan_at: datetime | None = None

    model_config = {"from_attributes": False}
