import uuid
from datetime import datetime
from pydantic import BaseModel


class SiteAuditCheck(BaseModel):
    id: str
    label: str
    status: str  # "pass" | "warn" | "fail" | "unknown"
    detail: str
    fix: str


class SiteAuditResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    checks: list[SiteAuditCheck]
    passed: int
    warned: int
    failed: int
    unknown: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SiteAuditLatestResponse(BaseModel):
    audit: SiteAuditResponse
    fixed: list[str]
    regressed: list[str]
    has_previous: bool


class CompetitorSiteAuditResponse(BaseModel):
    competitor_id: uuid.UUID
    name: str
    website: str | None
    checks: list[SiteAuditCheck]
    passed: int
    warned: int
    failed: int
    unknown: int
    note: str
