import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.core.constants import MISINFORMATION_SEVERITIES


class MisinformationFindingResponse(BaseModel):
    """Admin-side view of one finding. Admin-only surface: `quote` is verbatim
    AI text and `status` may still be unreviewed, so this schema must never be
    reused for a client-facing route."""
    id: uuid.UUID
    quote: str
    category: str
    category_label: str
    rule_key: str | None = None
    rule_text: str | None = None
    truth_fact_id: uuid.UUID | None = None
    truth_fact_version_id: uuid.UUID | None = None
    severity: str
    explanation: str
    status: str
    platform: str
    platform_label: str
    query_text: str
    detected_at: datetime
    reviewed_at: datetime | None = None
    resolved_at: datetime | None = None
    admin_note: str | None = None


class MisinformationQueueResponse(BaseModel):
    findings: list[MisinformationFindingResponse]
    # status → count, for the review-queue header.
    counts: dict[str, int]


class MisinformationReviewRequest(BaseModel):
    action: str
    note: str | None = None
    severity: str | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in ("confirm", "dismiss"):
            raise ValueError('action must be "confirm" or "dismiss"')
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str | None) -> str | None:
        if value is not None and value not in MISINFORMATION_SEVERITIES:
            raise ValueError("severity must be high, medium, or low")
        return value
