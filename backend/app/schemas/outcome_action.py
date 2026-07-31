import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.models.outcome_action import OUTCOME_ACTION_STATUSES, OUTCOME_ACTION_TYPES


OutcomeActionType = Literal[
    "content", "technical", "structured_data", "fact_correction",
    "accuracy_review", "authority", "local_presence",
    "competitor_response", "measurement",
]
OutcomeActionStatus = Literal[
    "detected", "recommended", "approved_internal", "in_progress",
    "waiting_client", "ready_to_publish", "published",
    "waiting_verification", "verified", "no_change",
    "superseded", "dismissed",
]

assert set(OutcomeActionType.__args__) == set(OUTCOME_ACTION_TYPES)
assert set(OutcomeActionStatus.__args__) == set(OUTCOME_ACTION_STATUSES)


class OutcomeActionCreate(BaseModel):
    source_kind: str
    source_ref: str | None = None
    title: str
    rationale: str
    action_type: OutcomeActionType
    priority: str
    confidence: str
    scan_id: uuid.UUID | None = None
    work_log_entry_id: uuid.UUID | None = None
    content_deliverable_id: uuid.UUID | None = None
    owner: str | None = None
    due_date: date | None = None
    destination_url: str | None = None
    client_safe_summary: str | None = None


class OutcomeActionPatch(BaseModel):
    owner: str | None = None
    due_date: date | None = None
    client_safe_summary: str | None = None
    destination_url: str | None = None
    dismissal_reason: str | None = None
    verification_result: str | None = None


class OutcomeActionOut(BaseModel):
    """Client-safe action representation, excluding specialist-source details."""

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    action_type: OutcomeActionType
    priority: str
    confidence: str
    status: OutcomeActionStatus
    owner: str | None
    due_date: date | None
    destination_url: str | None
    client_safe_summary: str | None
    published_at: datetime | None
    verified_at: datetime | None
    verification_result: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutcomeActionListResponse(BaseModel):
    actions: list[OutcomeActionOut]
    total: int
