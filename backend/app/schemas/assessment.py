import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ASSESSMENT_MAX_BULLETS


class AcceptRequest(BaseModel):
    # None = accept the suggested score as-is; a value adjusts it.
    final_score: int | None = None
    # The evidence as the admin edited it; None = the suggested bullets as-is.
    bullets: list[str] | None = Field(default=None, max_length=ASSESSMENT_MAX_BULLETS)
    # Required (service-enforced) when the score or the evidence was changed.
    reason: str | None = Field(default=None, max_length=1000)
    # Checklist assessments: per-criterion points {criterion_key: points}.
    points: dict[str, int] | None = None


class AssessmentCriterion(BaseModel):
    key: str
    label: str
    max: int
    basis: str
    points: int
    final_points: int | None = None
    evidence: str | None = None
    admin_hint: str | None = None  # admin-only; never on a client-facing schema


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dimension: str
    suggested_score: int
    final_score: int | None
    status: str
    evidence_bullets: list[str]
    raw_narrative: str | None  # admin-only surface; never used by client view
    generated_at: datetime
    reviewed_at: datetime | None
    final_bullets: list[str] | None = None
    adjustment_reason: str | None = None
    reviewed_by: str | None = None
    criteria: list[AssessmentCriterion] | None = None


class DimensionReviewStatus(BaseModel):
    """Where one manual dimension's review stands, for the admin Settings page."""

    dimension: str
    score: int | None
    reviewed_at: datetime | None
    reviewed_by: str | None
    adjustment_reason: str | None
    evidence: list[str]
    review_due: bool
    # "never_reviewed" | "stale" | "method_changed" | None
    due_reason: str | None
    criteria: list[AssessmentCriterion] | None = None


class ReviewDueItem(BaseModel):
    client_id: uuid.UUID
    client_name: str
    dimension: str
    last_reviewed_at: datetime | None
    due_reason: str
