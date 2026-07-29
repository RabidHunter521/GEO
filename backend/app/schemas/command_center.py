"""Response contract for the admin Command Center (Phase 1, Task 1).

Read-only aggregation over rows that already exist. Every field here must be
derivable from stored evidence — a field the schema cannot back with a real
column would imply tracking SeenBy does not do.
"""
import uuid

from pydantic import BaseModel


class MetricValue(BaseModel):
    """One headline number plus the kind of evidence behind it.

    `value` is None when there is nothing stored to report; `evidence_label`
    then reads "Unavailable" rather than dressing an absence up as a result.
    """
    value: float | None
    delta: float | None = None
    evidence_label: str


class CommandCenterMetrics(BaseModel):
    ai_presence: MetricValue
    accuracy: MetricValue
    growth_readiness: MetricValue
    business_impact: MetricValue


class PeriodStory(BaseModel):
    headline: str
    bullets: list[str] = []


class AttentionSummary(BaseModel):
    accuracy_risks: int
    overdue_actions: int
    stale_scan: bool


class DeliverySummary(BaseModel):
    """Work pipeline counts.

    Deliberately three fields. Nothing in the schema records a client-blocked
    state (work log entries are suggested|published|dismissed, remediation items
    are flagged|in_progress|corrected), so there is no "waiting for client"
    count to report honestly.
    """
    in_progress: int
    ready_to_publish: int
    completed_last_30d: int


class CommandCenterAction(BaseModel):
    id: uuid.UUID
    action_text: str
    priority: str
    reason: str


class CommandCenterResponse(BaseModel):
    metrics: CommandCenterMetrics
    period_story: PeriodStory
    attention: AttentionSummary
    delivery: DeliverySummary
    priority_actions: list[CommandCenterAction] = []
