import uuid
from datetime import date, datetime

from pydantic import BaseModel


class WorkLogEntryOut(BaseModel):
    id: uuid.UUID
    category: str
    category_label: str = ""
    description: str
    source: str
    status: str
    entry_date: date
    created_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class WorkLogCreateRequest(BaseModel):
    category: str
    description: str
    entry_date: date


class WorkLogPatchRequest(BaseModel):
    category: str | None = None
    description: str | None = None
    entry_date: date | None = None
    status: str | None = None
