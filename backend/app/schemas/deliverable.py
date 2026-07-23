import uuid
from datetime import datetime
from pydantic import BaseModel


class DeliverableCreate(BaseModel):
    type: str
    competitor_id: uuid.UUID | None = None


class DeliverableUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    status: str | None = None  # only "reviewed" accepted


class DeliverableResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    type: str
    competitor_id: uuid.UUID | None
    title: str
    body_md: str
    status: str
    generated_at: datetime
    reviewed_at: datetime | None
    # source_context is deliberately NOT exposed — admin-only provenance kept
    # server-side; the UI doesn't need it.

    model_config = {"from_attributes": True}
