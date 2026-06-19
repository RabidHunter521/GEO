import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator

from app.core.constants import REMEDIATION_STATUSES


class RemediationItemResponse(BaseModel):
    """Admin-side view of a tracked remediation item (full detail)."""
    id: uuid.UUID
    item_type: str
    platform: str
    label: str
    detail: str | None = None
    status: str
    first_seen_at: datetime
    resolved_at: datetime | None = None

    model_config = {"from_attributes": True}


class RemediationStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in REMEDIATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(REMEDIATION_STATUSES)}")
        return value
