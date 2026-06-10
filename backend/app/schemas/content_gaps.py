import uuid
from datetime import datetime
from pydantic import BaseModel


class TopicItem(BaseModel):
    topic: str
    status: str  # strong | weak | missing


class EntityItem(BaseModel):
    entity: str
    covered: bool


class ContentMetrics(BaseModel):
    word_count: int = 0
    h1_count: int = 0
    faq_count: int = 0
    blog_count: int = 0
    schema_present: bool = False


class ContentAnalysisResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    status: str
    topics_json: list[TopicItem]
    entities_json: list[EntityItem]
    entity_coverage_score: float
    content_metrics_json: ContentMetrics
    content_quality_recommendation: str | None = None
    pages_crawled: int
    analyzed_at: datetime

    model_config = {"from_attributes": True}
