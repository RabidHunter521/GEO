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


class WorkLogSuggestionOut(WorkLogEntryOut):
    """A suggestion plus the client it belongs to, for the cross-client queue.

    Extends WorkLogEntryOut rather than redefining the shared fields — two
    independent models describing one row is how Phase 4 shipped a field with
    two different values.

    `client_name` defaults to "" and is assigned after model_validate, exactly
    as `category_label` already is: neither exists on the WorkLogEntry ORM
    object, so validation would fail if they were required.
    """
    client_id: uuid.UUID
    client_name: str = ""
