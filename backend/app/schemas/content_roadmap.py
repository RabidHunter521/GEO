import uuid
from datetime import datetime
from pydantic import BaseModel, model_validator


class RoadmapItem(BaseModel):
    week: int = 1  # 1–12 (which week of the 90-day / 12-week plan)
    theme: str
    priority: str  # high | medium | low
    target_queries: list[str] = []
    competitors_winning: list[str] = []
    content_type: str  # e.g. "Blog post", "Comparison page", "FAQ"
    suggested_title: str
    rationale: str
    # Full article draft, generated on demand when the title is opened.
    article_content: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _week_from_legacy_month(cls, data):
        # Roadmaps generated under the old monthly model stored "month" (1–3).
        if isinstance(data, dict) and "week" not in data and "month" in data:
            data = {**data, "week": data["month"]}
        return data


class ContentRoadmapResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    status: str
    roadmap_json: list[RoadmapItem]
    source_query_count: int
    generated_at: datetime

    model_config = {"from_attributes": True}
