import uuid
from datetime import datetime
from pydantic import BaseModel


class RoadmapItem(BaseModel):
    month: int  # 1, 2, or 3 (which 30-day block of the 90-day plan)
    theme: str
    priority: str  # high | medium | low
    target_queries: list[str] = []
    competitors_winning: list[str] = []
    content_type: str  # e.g. "Blog post", "Comparison page", "FAQ"
    suggested_title: str
    rationale: str


class ContentRoadmapResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    status: str
    roadmap_json: list[RoadmapItem]
    source_query_count: int
    generated_at: datetime

    model_config = {"from_attributes": True}
