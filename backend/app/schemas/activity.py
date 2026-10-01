import uuid
from datetime import datetime
from pydantic import BaseModel


class ActivityLogEntry(BaseModel):
    id: uuid.UUID
    event_type: str
    note: str
    created_at: datetime
    # Admin-only: who caused the event. None = System (Celery, scripts).
    actor_name: str | None = None

    model_config = {"from_attributes": True}
