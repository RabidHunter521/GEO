import uuid
from datetime import datetime
from pydantic import BaseModel


class ActivityLogEntry(BaseModel):
    id: uuid.UUID
    event_type: str
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}
