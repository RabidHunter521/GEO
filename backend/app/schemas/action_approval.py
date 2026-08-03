from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ActionApprovalPublic(BaseModel):
    business_name: str
    action_title: str
    client_safe_summary: str | None
    deliverable_url: str | None
    destination_url: str | None
    expires_at: datetime


class ActionApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "request_changes"]
    comment: str | None = Field(default=None, max_length=2000)


class ActionApprovalDecisionOut(BaseModel):
    status: Literal["recorded"]
    decision: Literal["approved", "request_changes"]
