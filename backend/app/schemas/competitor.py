import uuid
from pydantic import BaseModel, Field


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=500)


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
