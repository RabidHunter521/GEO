"""Strict admin payloads for the versioned Business Truth Vault."""

import uuid
import unicodedata
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, ValidationError, field_validator


class TruthValue(BaseModel):
    value: str | int | float | bool | list | dict | None
    display_value: str

    model_config = {"extra": "forbid"}


class TruthFactCreate(BaseModel):
    fact_type: str = Field(min_length=1, max_length=64)
    fact_key: str = Field(min_length=1, max_length=255)
    location_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


class TruthFactVersionDraft(BaseModel):
    value: TruthValue
    source_url: str | None = Field(default=None, max_length=2048)
    reviewer_note: str | None = None
    effective_from: datetime

    model_config = {"extra": "forbid"}

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            validated_url = TypeAdapter(HttpUrl).validate_python(value)
        except ValidationError as exc:
            raise ValueError("source_url must be an absolute HTTP(S) URL") from exc
        if any(unicodedata.category(character) == "Cc" for character in value):
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return str(validated_url)


class TruthFactApprove(BaseModel):
    approved_by: str = Field(min_length=1, max_length=255)

    model_config = {"extra": "forbid"}


class TruthFactRetire(BaseModel):
    effective_at: datetime

    model_config = {"extra": "forbid"}


class TruthFactVersionOut(BaseModel):
    id: uuid.UUID
    truth_fact_id: uuid.UUID
    value: TruthValue = Field(validation_alias="value_json")
    status: str
    source_url: str | None
    reviewer_note: str | None
    effective_from: datetime | None
    effective_to: datetime | None
    approved_at: datetime | None
    approved_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TruthFactOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    location_id: uuid.UUID | None
    fact_type: str
    fact_key: str
    created_at: datetime
    versions: list[TruthFactVersionOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TruthFactListResponse(BaseModel):
    facts: list[TruthFactOut]
    total: int
