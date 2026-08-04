"""Validated admin payloads for the governed tracked-query portfolio.

`source`, `intent`, `buyer_stage`, and `risk_level` are constrained with
`Literal` at this API boundary (the model column is a plain varchar — see
`app/models/tracked_query.py`), matching the existing convention in
`app/schemas/outcome_action.py` rather than introducing a Python `enum.Enum`
class, which this codebase does not otherwise use.

`intent` reuses the scan engine's four established query categories (see
`app/services/query_builder.py` and CLAUDE.md section 5) so a tracked query
slots directly into the same taxonomy the scan engine already scores against.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.tracked_query import TrackedQuery


TrackedQuerySource = Literal["manual", "scan_generated", "competitor_gap", "traffic_import"]
TrackedQueryIntent = Literal["brand", "comparison", "recommendation", "local"]
TrackedQueryBuyerStage = Literal["awareness", "consideration", "decision"]
TrackedQueryRiskLevel = Literal["low", "standard", "elevated", "critical"]


class TrackedQueryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source: TrackedQuerySource
    intent: TrackedQueryIntent
    buyer_stage: TrackedQueryBuyerStage | None = None
    service_key: str | None = Field(default=None, max_length=64)
    risk_level: TrackedQueryRiskLevel = "standard"
    location_id: uuid.UUID | None = None
    demand_weight: float = Field(default=0.5, ge=0, le=1)
    # Scoring-only inputs: folded into priority_score at write time, never
    # persisted as their own columns (see tracked_query_service). Omitted
    # values score as neutral (0.5), same convention as
    # outcome_priority_service.NEUTRAL_INPUT_VALUE.
    recent_change_weight: float | None = Field(default=None, ge=0, le=1)
    business_value_weight: float | None = Field(default=None, ge=0, le=1)

    model_config = {"extra": "forbid"}


class TrackedQueryPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    source: TrackedQuerySource | None = None
    intent: TrackedQueryIntent | None = None
    buyer_stage: TrackedQueryBuyerStage | None = None
    service_key: str | None = Field(default=None, max_length=64)
    risk_level: TrackedQueryRiskLevel | None = None
    location_id: uuid.UUID | None = None
    demand_weight: float | None = Field(default=None, ge=0, le=1)
    recent_change_weight: float | None = Field(default=None, ge=0, le=1)
    business_value_weight: float | None = Field(default=None, ge=0, le=1)

    model_config = {"extra": "forbid"}


class TrackedQueryOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    location_id: uuid.UUID | None
    text: str
    normalized_text: str
    source: str
    intent: str
    buyer_stage: str | None
    service_key: str | None
    risk_level: str
    demand_weight: float
    priority_score: float
    # Computed fresh on every read from the persisted fields above — never
    # stored, so it can never drift from what the row currently holds. See
    # tracked_query_service.priority_reasons_for.
    priority_reasons: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, tracked_query: TrackedQuery, reasons: list[str]) -> "TrackedQueryOut":
        return cls(
            id=tracked_query.id,
            client_id=tracked_query.client_id,
            location_id=tracked_query.location_id,
            text=tracked_query.text,
            normalized_text=tracked_query.normalized_text,
            source=tracked_query.source,
            intent=tracked_query.intent,
            buyer_stage=tracked_query.buyer_stage,
            service_key=tracked_query.service_key,
            risk_level=tracked_query.risk_level,
            demand_weight=tracked_query.demand_weight,
            priority_score=tracked_query.priority_score,
            priority_reasons=reasons,
            is_active=tracked_query.is_active,
            created_at=tracked_query.created_at,
            updated_at=tracked_query.updated_at,
        )
