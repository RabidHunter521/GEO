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


class ScanQueryResultResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    platform: str = "gemini"
    competitor_id: uuid.UUID | None = None
    competitor_name: str | None = None
    category: str
    query_text: str
    response_text: str | None = None
    brand_detected: bool
    hallucination_flagged: bool = False
    recommendation_position: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanWithResultsResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    platform: str
    status: str
    triggered_at: datetime
    completed_at: datetime | None = None
    results: list[ScanQueryResultResponse] = []

    model_config = {"from_attributes": True}
