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
    # "manual" | "ga4" — how this month's number was produced.
    source: str = "manual"
    # Per-referrer session counts (ga4 rows only), e.g. {"chatgpt.com": 140}.
    breakdown: dict[str, int] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Ga4SyncReportResponse(BaseModel):
    synced_periods: list[date] = []
    skipped_manual: list[date] = []
    error: str | None = None
