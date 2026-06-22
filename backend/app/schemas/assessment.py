import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AcceptRequest(BaseModel):
    # None = accept the suggested score as-is; a value adjusts it.
    final_score: int | None = None


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dimension: str
    suggested_score: int
    final_score: int | None
    status: str
    evidence_bullets: list[str]
    raw_narrative: str | None  # admin-only surface; never used by client view
    generated_at: datetime
    reviewed_at: datetime | None
