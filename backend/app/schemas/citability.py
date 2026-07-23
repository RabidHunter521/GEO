import uuid
from datetime import datetime
from pydantic import BaseModel


class PageAuditRequest(BaseModel):
    url: str


class PageAuditCheck(BaseModel):
    id: str
    label: str
    status: str  # "pass" | "warn" | "fail"
    detail: str
    points: int  # earned


class PageAuditSuggestion(BaseModel):
    section: str
    issue: str
    rewrite: str


class PageAuditResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    url: str
    score: int
    checks: list[PageAuditCheck]
    suggestions: list[PageAuditSuggestion]
    suggestions_failed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PageAuditListItem(BaseModel):
    id: uuid.UUID
    url: str
    score: int
    previous_score: int | None
    created_at: datetime
