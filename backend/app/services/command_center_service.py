# backend/app/services/command_center_service.py
"""Admin Command Center aggregation (Phase 1, Task 1).

A read-only projection over rows other services already produce: GeoScore,
Scan, RemediationItem, WorkLogEntry, ActionRecommendation and
AiTrafficSnapshot. It adds no tables and generates nothing.

Two rules shape every function here:

1. No LLM. `action_center_service` already generates ActionRecommendation rows
   via Claude after each scan; this service only *reads* the open ones. An
   admin opening a dashboard must never trigger a paid generation.
2. No number without evidence. Where nothing is stored the metric is None and
   labelled "Unavailable" — a zero would read as a measured result.
"""
from datetime import timedelta

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.constants import (
    COMMAND_CENTER_DELIVERY_WINDOW_DAYS,
    DEFAULT_SCAN_CADENCE_DAYS,
    EVIDENCE_OBSERVED,
    EVIDENCE_REVIEWED,
    EVIDENCE_UNAVAILABLE,
    MAX_OPEN_ACTIONS,
    SCORE_DISPLAY_LABEL,
    SCORE_VERSION,
)
from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.work_log_entry import WorkLogEntry
from app.prompts.action_center import DIMENSION_LABELS
from app.schemas.command_center import (
    AttentionSummary,
    CommandCenterAction,
    CommandCenterMetrics,
    CommandCenterResponse,
    DeliverySummary,
    MetricValue,
    PeriodStory,
)

# Accuracy is scoped to the item types a human reviews and drives through
# flagged -> in_progress -> corrected: hallucinations AND admin-confirmed
# misinformation findings (misinformation_service.py creates a "misinformation"
# RemediationItem when an admin confirms a finding). content_gap items are
# delivery work, not accuracy findings. Plan Task 1 Step 3 requires confirmed
# open misinformation/remediation counts to be part of this metric — leaving
# misinformation out gave a false all-clear on the highest-stakes axis.
_ACCURACY_ITEM_TYPES = ("hallucination", "misinformation")
# Uncorrected statuses of the remediation lifecycle.
_OPEN_REMEDIATION_STATUSES = ("flagged", "in_progress")

# Composite scores carry their formula version so a reader can tell which
# version produced the number (CLAUDE.md §4).
_GROWTH_READINESS_EVIDENCE_LABEL = f"Composite ({SCORE_VERSION})"


def _metric(value: float | None, delta: float | None, evidence_label: str) -> MetricValue:
    """Absent evidence is reported as absent, never as zero."""
    if value is None:
        return MetricValue(value=None, delta=None, evidence_label=EVIDENCE_UNAVAILABLE)
    return MetricValue(value=float(value), delta=delta, evidence_label=evidence_label)


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(float(current) - float(previous), 1)


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _latest_scores(client: Client, db: Session) -> tuple[GeoScore | None, GeoScore | None]:
    """The two newest scores, newest first. id breaks computed_at ties."""
    rows = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
        .limit(2)
        .all()
    )
    return (
        rows[0] if rows else None,
        rows[1] if len(rows) > 1 else None,
    )


def _latest_traffic(client: Client, db: Session) -> tuple[int | None, int | None]:
    """AI-referral visitor counts for the two newest recorded months."""
    rows = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client.id)
        .order_by(desc(AiTrafficSnapshot.period), desc(AiTrafficSnapshot.id))
        .limit(2)
        .all()
    )
    return (
        rows[0].ai_visitors if rows else None,
        rows[1].ai_visitors if len(rows) > 1 else None,
    )


def _accuracy(client: Client, db: Session) -> float | None:
    """Share of reviewed accuracy findings that have been corrected.

    Denominator is the client's own reviewed findings, not scanned queries — a
    client with one finding and one fix is at 100%, and a client with no
    findings has no accuracy evidence at all (None).
    """
    rows = (
        db.query(RemediationItem.status, func.count(RemediationItem.id))
        .filter(
            RemediationItem.client_id == client.id,
            RemediationItem.item_type.in_(_ACCURACY_ITEM_TYPES),
        )
        .group_by(RemediationItem.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    corrected = counts.get("corrected", 0)
    total = corrected + sum(counts.get(s, 0) for s in _OPEN_REMEDIATION_STATUSES)
    if total == 0:
        return None
    return round(100.0 * corrected / total, 1)


def _attention(client: Client, db: Session) -> AttentionSummary:
    cadence_cutoff = utcnow() - timedelta(days=DEFAULT_SCAN_CADENCE_DAYS)

    accuracy_risks = (
        db.query(func.count(RemediationItem.id))
        .filter(
            RemediationItem.client_id == client.id,
            RemediationItem.item_type.in_(_ACCURACY_ITEM_TYPES),
            RemediationItem.status.in_(_OPEN_REMEDIATION_STATUSES),
        )
        .scalar()
    ) or 0

    # ActionRecommendation has no due date, so "overdue" is age-based: an action
    # still open after a full review cycle has not been acted on.
    overdue_actions = (
        db.query(func.count(ActionRecommendation.id))
        .filter(
            ActionRecommendation.client_id == client.id,
            ActionRecommendation.status == "open",
            ActionRecommendation.generated_at < cadence_cutoff,
        )
        .scalar()
    ) or 0

    recent_scan = (
        db.query(func.count(Scan.id))
        .filter(
            Scan.client_id == client.id,
            Scan.status == "completed",
            Scan.completed_at.isnot(None),
            Scan.completed_at >= cadence_cutoff,
        )
        .scalar()
    ) or 0

    return AttentionSummary(
        accuracy_risks=accuracy_risks,
        overdue_actions=overdue_actions,
        stale_scan=recent_scan == 0,
    )


def _delivery(client: Client, db: Session) -> DeliverySummary:
    """Work pipeline counts read straight off stored statuses.

    `in_progress` comes from remediation items — the only place the schema
    records work actively underway. `ready_to_publish` is the suggested work-log
    backlog awaiting the admin's publish decision.
    """
    published_cutoff = utcnow() - timedelta(days=COMMAND_CENTER_DELIVERY_WINDOW_DAYS)

    in_progress = (
        db.query(func.count(RemediationItem.id))
        .filter(
            RemediationItem.client_id == client.id,
            RemediationItem.status == "in_progress",
        )
        .scalar()
    ) or 0

    ready_to_publish = (
        db.query(func.count(WorkLogEntry.id))
        .filter(
            WorkLogEntry.client_id == client.id,
            WorkLogEntry.status == "suggested",
        )
        .scalar()
    ) or 0

    completed_last_30d = (
        db.query(func.count(WorkLogEntry.id))
        .filter(
            WorkLogEntry.client_id == client.id,
            WorkLogEntry.status == "published",
            WorkLogEntry.published_at.isnot(None),
            WorkLogEntry.published_at >= published_cutoff,
        )
        .scalar()
    ) or 0

    return DeliverySummary(
        in_progress=in_progress,
        ready_to_publish=ready_to_publish,
        completed_last_30d=completed_last_30d,
    )


def _action_reason(action: ActionRecommendation) -> str:
    """Composite-impact string, prefixed with the dimension it targets so an
    admin scanning several open actions doesn't have to infer it from
    action_text. `DIMENSION_LABELS` (app/prompts/action_center.py) is the
    single source of truth for the five dimension display names — an
    unrecognized/legacy value falls back to the raw stored key rather than
    raising, since this is a read-only projection over existing rows."""
    dimension_label = DIMENSION_LABELS.get(action.dimension, action.dimension)
    impact = float(action.estimated_impact or 0.0)
    if impact <= 0:
        return f"{dimension_label}: open action with no estimated {SCORE_DISPLAY_LABEL} impact recorded"
    return f"{dimension_label}: estimated +{impact:.1f} points to {SCORE_DISPLAY_LABEL}"


def _priority_actions(client: Client, db: Session) -> list[CommandCenterAction]:
    """Existing open recommendations, highest estimated impact first.

    Reads only. Regeneration belongs to action_center_service, which runs after
    a scan.
    """
    rows = (
        db.query(ActionRecommendation)
        .filter(
            ActionRecommendation.client_id == client.id,
            ActionRecommendation.status == "open",
        )
        .order_by(
            desc(ActionRecommendation.estimated_impact),
            desc(ActionRecommendation.generated_at),
            desc(ActionRecommendation.id),
        )
        .limit(MAX_OPEN_ACTIONS)
        .all()
    )
    return [
        CommandCenterAction(
            id=row.id,
            action_text=row.action_text,
            priority=row.priority,
            reason=_action_reason(row),
        )
        for row in rows
    ]


def _change_headline(current: float | None, previous: float | None) -> str:
    if current is None:
        return "Baseline measurement is being prepared"
    if previous is None:
        return f"AI Presence baseline established at {current:.1f}%"
    delta = round(current - previous, 1)
    if delta > 0:
        return f"AI Presence improved by {delta:.1f} points"
    if delta < 0:
        return f"AI Presence declined by {abs(delta):.1f} points"
    return "AI Presence held steady"


def _bullets(
    growth_readiness: float | None,
    growth_readiness_delta: float | None,
    accuracy_risks: int,
    completed_last_30d: int,
    ai_visitors: int | None,
) -> list[str]:
    """Plain restatements of stored numbers — no interpretation, no forecasts."""
    bullets: list[str] = []

    if growth_readiness is not None and growth_readiness_delta is not None:
        if growth_readiness_delta > 0:
            direction = f"up {growth_readiness_delta:.1f} points"
        elif growth_readiness_delta < 0:
            direction = f"down {abs(growth_readiness_delta):.1f} points"
        else:
            direction = "unchanged"
        bullets.append(f"{SCORE_DISPLAY_LABEL} {direction} at {growth_readiness:.1f}")

    if accuracy_risks:
        noun = _plural(accuracy_risks, "accuracy risk", "accuracy risks")
        bullets.append(f"{accuracy_risks} {noun} still open for correction")

    if completed_last_30d:
        noun = _plural(completed_last_30d, "delivery item", "delivery items")
        bullets.append(
            f"{completed_last_30d} {noun} published in the last "
            f"{COMMAND_CENTER_DELIVERY_WINDOW_DAYS} days"
        )

    if ai_visitors:
        noun = _plural(ai_visitors, "visitor", "visitors")
        bullets.append(
            f"{ai_visitors} {noun} recorded arriving from AI assistants in the latest month"
        )

    return bullets


def build_command_center(client: Client, db: Session) -> CommandCenterResponse:
    """Aggregate one client's stored evidence into the Command Center contract."""
    latest_score, previous_score = _latest_scores(client, db)
    latest_visitors, previous_visitors = _latest_traffic(client, db)

    ai_presence = latest_score.ai_citability if latest_score else None
    previous_ai_presence = previous_score.ai_citability if previous_score else None
    growth_readiness = latest_score.overall_score if latest_score else None
    previous_growth_readiness = previous_score.overall_score if previous_score else None
    growth_readiness_delta = _delta(growth_readiness, previous_growth_readiness)

    attention = _attention(client, db)
    delivery = _delivery(client, db)

    metrics = CommandCenterMetrics(
        ai_presence=_metric(
            ai_presence, _delta(ai_presence, previous_ai_presence), EVIDENCE_OBSERVED
        ),
        accuracy=_metric(_accuracy(client, db), None, EVIDENCE_REVIEWED),
        growth_readiness=_metric(
            growth_readiness, growth_readiness_delta, _GROWTH_READINESS_EVIDENCE_LABEL
        ),
        business_impact=_metric(
            latest_visitors, _delta(latest_visitors, previous_visitors), EVIDENCE_OBSERVED
        ),
    )

    return CommandCenterResponse(
        metrics=metrics,
        period_story=PeriodStory(
            headline=_change_headline(ai_presence, previous_ai_presence),
            bullets=_bullets(
                growth_readiness,
                growth_readiness_delta,
                attention.accuracy_risks,
                delivery.completed_last_30d,
                latest_visitors,
            ),
        ),
        attention=attention,
        delivery=delivery,
        priority_actions=_priority_actions(client, db),
    )
