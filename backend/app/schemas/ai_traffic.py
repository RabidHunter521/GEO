import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field


class AiTrafficSnapshotUpsert(BaseModel):
    period: date
    ai_visitors: int = Field(ge=0)


class AiTrafficSnapshotResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    period: date
    ai_visitors: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
