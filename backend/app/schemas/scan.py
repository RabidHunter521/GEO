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
    # Benchmark row (admin UI labels it "benchmark — left alone").
    is_control: bool = False
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


class ScanDiffQuery(BaseModel):
    platform: str
    category: str
    query_text: str


class ScanDiffResponse(BaseModel):
    latest_scan_id: uuid.UUID | None = None
    previous_scan_id: uuid.UUID | None = None
    latest_scan_at: datetime | None = None
    previous_scan_at: datetime | None = None
    latest_visibility: float | None = None
    previous_visibility: float | None = None
    newly_seen: list[ScanDiffQuery] = []
    newly_unseen: list[ScanDiffQuery] = []
    has_comparison: bool = False
