"""Admin Command Center aggregation (Phase 1, Task 1).

Read-only aggregation over rows that already exist. Every assertion here seeds
real ORM rows and reads them back through the service — nothing is mocked, so a
test passing means the aggregation genuinely reads stored evidence.
"""
from datetime import date, timedelta
from unittest.mock import patch

from app.core.constants import (
    COMMAND_CENTER_DELIVERY_WINDOW_DAYS,
    DEFAULT_SCAN_CADENCE_DAYS,
    MAX_OPEN_ACTIONS,
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
from app.services.command_center_service import build_command_center


def _client(db) -> Client:
    c = Client(name="Acme Dental", website="acme.com", industry="dentist")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _scored_scan(db, client_id, *, ai: float, overall: float, days_ago: int = 0) -> GeoScore:
    when = utcnow() - timedelta(days=days_ago)
    scan = Scan(client_id=client_id, status="completed", triggered_at=when, completed_at=when)
    db.add(scan)
    db.flush()
    score = GeoScore(
        client_id=client_id,
        scan_id=scan.id,
        ai_citability=ai,
        overall_score=overall,
        computed_at=when,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def _hallucination(db, client_id, *, label: str, status: str) -> RemediationItem:
    item = RemediationItem(
        client_id=client_id,
        item_type="hallucination",
        platform="chatgpt",
        label=label,
        status=status,
    )
    db.add(item)
    db.commit()
    return item


def _work_log(db, client_id, *, status: str, published_days_ago: int | None = None) -> WorkLogEntry:
    published_at = None if published_days_ago is None else utcnow() - timedelta(days=published_days_ago)
    entry = WorkLogEntry(
        client_id=client_id,
        category="content",
        description="Published the new services page.",
        status=status,
        entry_date=date.today(),
        published_at=published_at,
    )
    db.add(entry)
    db.commit()
    return entry


def _open_action(db, client_id, *, text: str, impact: float = 4.0, priority: str = "medium",
                 days_ago: int = 0, status: str = "open",
                 dimension: str = "content_quality") -> ActionRecommendation:
    action = ActionRecommendation(
        client_id=client_id,
        action_text=text,
        dimension=dimension,
        estimated_impact=impact,
        priority=priority,
        status=status,
        generated_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _seeded_client(db) -> Client:
    """One client, two scores, one open action, one flagged remediation item,
    one published work-log entry, one traffic snapshot."""
    c = _client(db)
    _scored_scan(db, c.id, ai=30.0, overall=52.0, days_ago=14)
    _scored_scan(db, c.id, ai=45.0, overall=60.0, days_ago=0)
    _open_action(db, c.id, text="Publish the service page")
    _hallucination(db, c.id, label="Does Acme Dental fit braces?", status="flagged")
    _work_log(db, c.id, status="published", published_days_ago=2)
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1), ai_visitors=120))
    db.commit()
    return c


# --- contract assertions from the task brief --------------------------------

def test_build_command_center_reads_stored_evidence(db):
    client = _seeded_client(db)

    result = build_command_center(client, db)

    assert result.metrics.ai_presence.value == 45.0
    assert result.metrics.growth_readiness.value == 60.0
    assert result.attention.accuracy_risks == 1
    assert result.delivery.completed_last_30d == 1
    assert result.priority_actions[0].action_text == "Publish the service page"
    assert result.period_story.headline == "AI Presence improved by 15.0 points"


def test_build_command_center_with_no_data(db):
    client = _client(db)

    result = build_command_center(client, db)

    assert result.metrics.ai_presence.value is None
    assert result.period_story.headline == "Baseline measurement is being prepared"
    assert result.priority_actions == []


# --- metrics -----------------------------------------------------------------

def test_metric_deltas_compare_the_two_newest_scores(db):
    client = _seeded_client(db)

    result = build_command_center(client, db)

    assert result.metrics.ai_presence.delta == 15.0
    assert result.metrics.growth_readiness.delta == 8.0


def test_single_score_has_no_delta(db):
    client = _client(db)
    _scored_scan(db, client.id, ai=45.0, overall=60.0)

    result = build_command_center(client, db)

    assert result.metrics.ai_presence.value == 45.0
    assert result.metrics.ai_presence.delta is None
    assert result.period_story.headline == "AI Presence baseline established at 45.0%"


def test_headline_reports_a_decline(db):
    client = _client(db)
    _scored_scan(db, client.id, ai=50.0, overall=60.0, days_ago=14)
    _scored_scan(db, client.id, ai=42.5, overall=58.0, days_ago=0)

    result = build_command_center(client, db)

    assert result.period_story.headline == "AI Presence declined by 7.5 points"


def test_headline_reports_no_change(db):
    client = _client(db)
    _scored_scan(db, client.id, ai=50.0, overall=60.0, days_ago=14)
    _scored_scan(db, client.id, ai=50.0, overall=60.0, days_ago=0)

    result = build_command_center(client, db)

    assert result.period_story.headline == "AI Presence held steady"


def test_evidence_labels_use_the_phase_0_vocabulary(db):
    client = _seeded_client(db)

    metrics = build_command_center(client, db).metrics

    assert metrics.ai_presence.evidence_label == "Observed"
    assert metrics.business_impact.evidence_label == "Observed"
    assert metrics.accuracy.evidence_label == "Reviewed"
    assert metrics.growth_readiness.evidence_label == f"Composite ({SCORE_VERSION})"


def test_unavailable_metrics_are_labelled_unavailable(db):
    client = _client(db)

    metrics = build_command_center(client, db).metrics

    for metric in (metrics.ai_presence, metrics.accuracy,
                   metrics.growth_readiness, metrics.business_impact):
        assert metric.value is None
        assert metric.delta is None
        assert metric.evidence_label == "Unavailable"


def test_accuracy_is_corrected_over_all_reviewed_hallucinations(db):
    client = _client(db)
    _hallucination(db, client.id, label="q1", status="corrected")
    _hallucination(db, client.id, label="q2", status="corrected")
    _hallucination(db, client.id, label="q3", status="flagged")
    _hallucination(db, client.id, label="q4", status="in_progress")

    result = build_command_center(client, db)

    assert result.metrics.accuracy.value == 50.0


def test_accuracy_is_none_without_reviewed_hallucinations(db):
    client = _client(db)
    # A content_gap item is delivery work, not an accuracy finding.
    db.add(RemediationItem(
        client_id=client.id, item_type="content_gap", platform="", label="best dentist",
        status="flagged",
    ))
    db.commit()

    result = build_command_center(client, db)

    assert result.metrics.accuracy.value is None
    assert result.metrics.accuracy.evidence_label == "Unavailable"


def test_business_impact_reads_the_newest_traffic_snapshot(db):
    client = _client(db)
    db.add(AiTrafficSnapshot(client_id=client.id, period=date(2026, 6, 1), ai_visitors=80))
    db.add(AiTrafficSnapshot(client_id=client.id, period=date(2026, 7, 1), ai_visitors=120))
    db.commit()

    result = build_command_center(client, db)

    assert result.metrics.business_impact.value == 120.0
    assert result.metrics.business_impact.delta == 40.0


# --- attention ---------------------------------------------------------------

def test_overdue_actions_are_open_actions_older_than_the_scan_cadence(db):
    client = _client(db)
    _open_action(db, client.id, text="Old and open", days_ago=DEFAULT_SCAN_CADENCE_DAYS + 1)
    _open_action(db, client.id, text="Fresh and open", days_ago=1)
    _open_action(db, client.id, text="Old but done",
                 days_ago=DEFAULT_SCAN_CADENCE_DAYS + 1, status="done")

    result = build_command_center(client, db)

    assert result.attention.overdue_actions == 1


def test_stale_scan_true_when_last_completed_scan_predates_the_cadence(db):
    client = _client(db)
    _scored_scan(db, client.id, ai=45.0, overall=60.0, days_ago=DEFAULT_SCAN_CADENCE_DAYS + 1)

    result = build_command_center(client, db)

    assert result.attention.stale_scan is True


def test_stale_scan_false_when_a_scan_completed_inside_the_cadence(db):
    client = _client(db)
    _scored_scan(db, client.id, ai=45.0, overall=60.0, days_ago=1)

    result = build_command_center(client, db)

    assert result.attention.stale_scan is False


def test_stale_scan_ignores_incomplete_scans(db):
    client = _client(db)
    db.add(Scan(client_id=client.id, status="failed", triggered_at=utcnow()))
    db.add(Scan(client_id=client.id, status="running", triggered_at=utcnow()))
    db.commit()

    result = build_command_center(client, db)

    assert result.attention.stale_scan is True


def test_accuracy_risks_count_only_uncorrected_hallucinations(db):
    client = _client(db)
    _hallucination(db, client.id, label="q1", status="flagged")
    _hallucination(db, client.id, label="q2", status="in_progress")
    _hallucination(db, client.id, label="q3", status="corrected")

    result = build_command_center(client, db)

    assert result.attention.accuracy_risks == 2


# --- delivery ----------------------------------------------------------------

def test_delivery_counts_split_by_stored_status(db):
    client = _client(db)
    _hallucination(db, client.id, label="q1", status="in_progress")
    _hallucination(db, client.id, label="q2", status="flagged")
    _work_log(db, client.id, status="suggested")
    _work_log(db, client.id, status="suggested")
    _work_log(db, client.id, status="published", published_days_ago=3)
    _work_log(db, client.id, status="dismissed")

    delivery = build_command_center(client, db).delivery

    assert delivery.in_progress == 1
    assert delivery.ready_to_publish == 2
    assert delivery.completed_last_30d == 1


def test_completed_last_30d_excludes_older_publications(db):
    client = _client(db)
    _work_log(db, client.id, status="published",
              published_days_ago=COMMAND_CENTER_DELIVERY_WINDOW_DAYS + 1)

    delivery = build_command_center(client, db).delivery

    assert delivery.completed_last_30d == 0


def test_delivery_summary_has_no_waiting_for_client_field(db):
    """Nothing in the schema tracks a client-blocked state, so the contract must
    not imply one (Phase 0: no surface claims more than stored evidence)."""
    client = _client(db)

    delivery = build_command_center(client, db).delivery

    assert not hasattr(delivery, "waiting_for_client")
    assert set(delivery.model_dump()) == {"in_progress", "ready_to_publish", "completed_last_30d"}


# --- priority actions --------------------------------------------------------

def test_priority_actions_read_existing_open_rows_highest_impact_first(db):
    client = _client(db)
    _open_action(db, client.id, text="Low impact", impact=1.0, priority="low")
    _open_action(db, client.id, text="High impact", impact=9.0, priority="high",
                 dimension="ai_citability")
    _open_action(db, client.id, text="Already done", impact=10.0, status="done")

    actions = build_command_center(client, db).priority_actions

    assert [a.action_text for a in actions] == ["High impact", "Low impact"]
    assert actions[0].priority == "high"
    assert "9.0" in actions[0].reason


def test_action_reason_includes_the_dimension_label(db):
    """An admin scanning several open actions must be able to tell which of the
    five Growth Readiness dimensions each one targets from `reason` alone,
    without inferring it from action_text (CLAUDE.md §4 canonical labels).
    "AI Citability" is not banned vocabulary — only cited/uncited, mentioned/not
    mentioned, citation rate etc. are (CLAUDE.md §2), and this endpoint is
    admin-only (require_api_key)."""
    client = _client(db)
    _open_action(db, client.id, text="Fix schema markup", impact=5.0,
                 dimension="structured_data")
    _open_action(db, client.id, text="Publish a comparison page", impact=3.0,
                 dimension="ai_citability")

    actions = build_command_center(client, db).priority_actions

    by_text = {a.action_text: a.reason for a in actions}
    assert "Structured Data" in by_text["Fix schema markup"]
    assert "AI Citability" in by_text["Publish a comparison page"]


def test_action_reason_falls_back_gracefully_for_unrecognized_dimension(db):
    """A dimension value outside the known five must not raise — this is a
    read-only projection over existing rows, so a legacy/bad value should
    degrade to the raw stored key rather than crashing the dashboard."""
    client = _client(db)
    _open_action(db, client.id, text="Mystery action", impact=2.0,
                 dimension="not_a_real_dimension")

    actions = build_command_center(client, db).priority_actions

    assert "not_a_real_dimension" in actions[0].reason


def test_priority_actions_are_capped_at_max_open_actions(db):
    client = _client(db)
    for i in range(MAX_OPEN_ACTIONS + 3):
        _open_action(db, client.id, text=f"Action {i}", impact=float(i))

    actions = build_command_center(client, db).priority_actions

    assert len(actions) == MAX_OPEN_ACTIONS


def test_priority_action_ids_match_the_stored_rows(db):
    client = _client(db)
    stored = _open_action(db, client.id, text="Publish the service page")

    actions = build_command_center(client, db).priority_actions

    assert actions[0].id == stored.id


# --- isolation ---------------------------------------------------------------

def test_another_clients_rows_are_never_counted(db):
    client = _seeded_client(db)
    other = Client(name="Other Co", website="other.com", industry="dentist")
    db.add(other)
    db.commit()
    db.refresh(other)
    _scored_scan(db, other.id, ai=99.0, overall=99.0)
    _open_action(db, other.id, text="Not mine")
    _hallucination(db, other.id, label="not mine", status="flagged")
    _work_log(db, other.id, status="published", published_days_ago=1)

    result = build_command_center(client, db)

    assert result.metrics.ai_presence.value == 45.0
    assert result.attention.accuracy_risks == 1
    assert result.delivery.completed_last_30d == 1
    assert [a.action_text for a in result.priority_actions] == ["Publish the service page"]


def test_period_story_bullets_are_built_only_from_stored_values(db):
    client = _seeded_client(db)

    story = build_command_center(client, db).period_story

    assert story.bullets  # seeded client has score movement, a risk and published work
    joined = " ".join(story.bullets).lower()
    for banned in ("cited", "uncited", "mentioned", "citation rate",
                   "ranking position", "visibility gap", "confidence score"):
        assert banned not in joined


def test_period_story_has_no_bullets_without_data(db):
    client = _client(db)

    story = build_command_center(client, db).period_story

    assert story.bullets == []


def test_aggregation_never_calls_an_llm(db):
    """Opening a dashboard must not trigger a paid generation. Recommendations
    are produced by action_center_service after a scan; this service only reads
    them."""
    client = _seeded_client(db)

    with patch(
        "app.services.claude_client.anthropic_client",
        side_effect=AssertionError("command center must not call Claude"),
    ):
        result = build_command_center(client, db)

    assert result.priority_actions[0].action_text == "Publish the service page"


def test_aggregation_writes_nothing(db):
    """Read-only: no rows created, changed or deleted by building the view."""
    client = _seeded_client(db)

    build_command_center(client, db)

    assert list(db.new) == []
    assert list(db.dirty) == []
    assert list(db.deleted) == []
