import uuid
from datetime import datetime
from pydantic import BaseModel


class TriggerScanRequest(BaseModel):
    client_id: uuid.UUID


class ScanResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    platform: str
    status: str
    triggered_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
