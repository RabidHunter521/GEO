"""Validated admin payloads for client-owned business locations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class OpeningPeriod(BaseModel):
    open: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def close_must_follow_open(self):
        if self.close <= self.open:
            raise ValueError("close must be after open")
        return self


class BusinessLocationFields(BaseModel):
    website: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    phone: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    service_area_json: list | dict | None = None
    hours_json: dict[str, list[OpeningPeriod]] | None = None
    booking_url: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("hours_json")
    @classmethod
    def require_full_week_when_hours_are_supplied(cls, hours_json):
        if hours_json is not None and set(hours_json) != set(WEEKDAYS):
            raise ValueError("hours_json must contain exactly seven day keys")
        return hours_json


class BusinessLocationCreate(BusinessLocationFields):
    name: str = Field(min_length=1, max_length=255)
    is_primary: bool = False


class BusinessLocationPatch(BusinessLocationFields):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_primary: bool | None = None


class BusinessLocationDeactivate(BaseModel):
    replacement_location_id: uuid.UUID | None = None

    model_config = {"extra": "forbid"}


class BusinessLocationOut(BusinessLocationFields):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    slug: str
    is_primary: bool
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
