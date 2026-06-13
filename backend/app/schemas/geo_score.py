import uuid
from datetime import datetime
from pydantic import BaseModel


class GeoScoreResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    scan_id: uuid.UUID
    ai_citability: float
    brand_authority: float
    content_quality: float
    technical_foundations: float
    structured_data: float
    overall_score: float
    platform_breakdown: dict | None = None
    computed_at: datetime

    model_config = {"from_attributes": True}
