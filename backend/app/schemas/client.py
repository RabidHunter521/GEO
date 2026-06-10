import uuid
from datetime import datetime
from pydantic import BaseModel


class ClientCreate(BaseModel):
    name: str
    website: str
    industry: str


class ClientUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    description: str | None = None
    target_audience: str | None = None
    city: str | None = None
    state: str | None = None
    contact_email: str | None = None
    brand_authority_score: int | None = None
    brand_authority_evidence: str | None = None
    content_quality_score: int | None = None
    content_quality_evidence: str | None = None
    score_drop_threshold: int | None = None


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
