import uuid
from datetime import datetime

from pydantic import BaseModel


class CausalityPointResponse(BaseModel):
    scan_id: uuid.UUID
    completed_at: datetime
    optimized_frequency: float | None = None
    control_frequency: float | None = None


class CausalityResponse(BaseModel):
    points: list[CausalityPointResponse]
