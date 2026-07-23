import uuid
from datetime import datetime
from pydantic import BaseModel


class ToolkitFilesResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    llms_txt: str
    schema_json: str
    robots_txt: str
    llms_full_txt: str | None = None
    generated_at: datetime
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    llms_full_verified: bool = False
    verified_at: datetime | None = None

    model_config = {"from_attributes": True}


class VerificationResult(BaseModel):
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    llms_full_verified: bool
    technical_foundations_updated: bool
    structured_data_updated: bool
