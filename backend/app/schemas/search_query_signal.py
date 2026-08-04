"""Validated payloads for the Search Console signal import/query API.

`device` is constrained with `Literal` at this API boundary (the model
column is a plain varchar — see `app/models/search_query_signal.py`),
matching the existing convention in `app/schemas/tracked_query.py` rather
than a Python `enum.Enum`, which this codebase does not otherwise use.
`country` is left as a plain bounded string rather than a Literal of every
ISO 3166-1 alpha-3 code — that enumeration belongs to Google's data, not to
this API's validation.

This module never carries OAuth tokens, refresh tokens, or unbounded raw
Google payloads — `SearchQuerySignalCreate` mirrors exactly the normalized
columns `search_query_signals` stores, nothing more.
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


SearchConsoleDevice = Literal["DESKTOP", "MOBILE", "TABLET", "UNKNOWN"]


class SearchQuerySignalCreate(BaseModel):
    location_id: uuid.UUID | None = None
    property_uri: str = Field(min_length=1, max_length=255)
    signal_date: date
    query: str = Field(min_length=1, max_length=2000)
    page: str = Field(min_length=1, max_length=2000)
    country: str = Field(default="ZZZ", min_length=1, max_length=3)
    device: SearchConsoleDevice = "UNKNOWN"
    clicks: int = Field(default=0, ge=0)
    impressions: int = Field(default=0, ge=0)
    ctr: float = Field(default=0.0, ge=0.0)
    position: float = Field(default=0.0, ge=0.0)

    model_config = {"extra": "forbid"}


class SearchConsoleSyncRequest(BaseModel):
    signals: list[SearchQuerySignalCreate] = Field(min_length=1, max_length=5000)

    model_config = {"extra": "forbid"}


class SearchConsoleSyncResult(BaseModel):
    inserted: int
    updated: int
    skipped: int
    total: int


class SearchConsoleSyncStatus(BaseModel):
    property_uris: list[str]
    total_signals: int
    earliest_signal_date: date | None
    latest_signal_date: date | None
    last_synced_at: datetime | None


class SearchQuerySignalOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    location_id: uuid.UUID | None
    property_uri: str
    signal_date: date
    query: str
    page: str
    country: str
    device: str
    clicks: int
    impressions: int
    ctr: float
    position: float
    synced_at: datetime

    model_config = {"from_attributes": True}
