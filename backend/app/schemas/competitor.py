import uuid
from pydantic import BaseModel


class CompetitorCreate(BaseModel):
    name: str
    website: str | None = None


class CompetitorResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    website: str | None = None

    model_config = {"from_attributes": True}


class CompetitorQueryBreakdown(BaseModel):
    category: str
    query_text: str
    brand_detected: bool


class CompetitorScore(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None = None
    ai_citability: float
    queries: list[CompetitorQueryBreakdown]
    is_winning: bool


class CompetitorIntelligenceResponse(BaseModel):
    client_ai_citability: float | None
    competitors: list[CompetitorScore]
    last_scan_at: str | None
