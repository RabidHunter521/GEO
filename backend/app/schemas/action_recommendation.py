import uuid
from datetime import datetime
from pydantic import BaseModel


class ActionRecommendationResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    action_text: str
    dimension: str
    estimated_impact: float
    priority: str
    status: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class ActionStatusUpdate(BaseModel):
    status: str
