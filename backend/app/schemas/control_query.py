import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ControlQueryCreate(BaseModel):
    query_text: str = Field(min_length=3, max_length=500)
    category: str = "recommendation"


class ControlQueryUpdate(BaseModel):
    active: bool


class ControlQueryResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    query_text: str
    category: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
