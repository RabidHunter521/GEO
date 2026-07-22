import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class GuaranteeCreate(BaseModel):
    metric: str = "ai_citability"
    target_value: int = Field(ge=1, le=100)
    deadline_date: date
    baseline_override: int | None = Field(default=None, ge=0, le=100)
    start_date: date | None = None


class GuaranteeResolve(BaseModel):
    outcome: str  # "met" | "missed" | "void" — validated in the service
    note: str | None = None


class GuaranteeResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    metric: str
    baseline_value: int
    target_value: int
    start_date: date
    deadline_date: date
    status: str
    resolved_at: datetime | None = None
    admin_note: str | None = None

    model_config = {"from_attributes": True}


class GuaranteeProgressResponse(BaseModel):
    """Flat progress payload: guarantee fields + derived pace numbers."""
    id: uuid.UUID
    metric: str
    baseline_value: int
    target_value: int
    start_date: date
    deadline_date: date
    status: str
    current_value: float | None = None
    points_needed: int
    points_gained: float
    days_total: int
    days_remaining: int
    state: str
