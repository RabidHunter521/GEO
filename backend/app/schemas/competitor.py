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
