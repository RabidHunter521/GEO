from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    r2_url: str
    period_start: datetime
    period_end: datetime
    overall_score: float
    generated_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}
