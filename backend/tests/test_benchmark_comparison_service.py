"""Phase 6 Task 4 — client-safe comparison contracts."""
from datetime import datetime

import pytest

from app.schemas.benchmark_comparison import (
    BenchmarkComparison,
    BenchmarkComparisonPublic,
    member_count_band,
    percentile_band,
)
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_comparison_service import (
    cohort_label,
    get_client_comparisons,
)
from app.services.benchmark_period import default_benchmark_period, previous_month_bounds
from app.services.benchmark_snapshot_service import (
    generate_ladder_snapshots,
    get_or_create_cohort,
)

from tests.test_benchmark_snapshot_service import (
    PERIOD_END,
    PERIOD_START,
    build_population,
    make_measured_client,
    spec_for,
)

APPROVED_AT = datetime(2026, 8, 1, 9, 0, 0)


def approved_cohort(db, scores=None):
    """A published cohort plus one extra client to compare against it."""
    build_population(db, scores or [float(n) for n in range(10, 110, 10)])
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    snapshots = generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    for snapshot in snapshots:
        if not snapshot.suppressed:
            snapshot.approved_at = APPROVED_AT
    db.commit()
    return snapshots


# --- band helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    "count,expected", [(10, "10–19"), (19, "10–19"), (20, "20–49"), (60, "50–99"), (250, "100+")]
)
def test_member_counts_are_banded_never_exact(count, expected):
    assert member_count_band(count) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(10.0, "bottom_quartile"), (50.0, "middle_half"), (95.0, "top_quartile")],
)
def test_percentile_band_is_coarse(value, expected):
    assert percentile_band(value, 25.0, 75.0) == expected


def test_a_client_exactly_on_a_quartile_edge_is_inside_the_middle(db):
    assert percentile_band(25.0, 25.0, 75.0) == "middle_half"
    assert percentile_band(75.0, 25.0, 75.0) == "middle_half"


# --- period defaults ----------------------------------------------------------


def test_period_defaults_to_the_last_closed_month():
    from datetime import date

    assert previous_month_bounds(date(2026, 8, 5)) == (date(2026, 7, 1), date(2026, 7, 31))


def test_a_half_specified_period_falls_back_rather_than_pairing_dates():
    from datetime import date

    start, end = default_benchmark_period(date(2026, 3, 1), None, today=date(2026, 8, 5))
    assert (start, end) == (date(2026, 7, 1), date(2026, 7, 31))


# --- comparisons --------------------------------------------------------------


def test_comparison_reports_a_band_not_a_rank(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=95.0)
    comparisons = get_client_comparisons(db, client, PERIOD_START, PERIOD_END)

    presence = next(c for c in comparisons if c.metric_key == "ai_presence_score")
    assert presence.suppressed is False
    assert presence.percentile_band == "top_quartile"
    assert presence.member_count_band == "10–19"
    assert presence.p50 is not None


def test_comparison_never_exposes_a_rank_field(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=95.0)
    comparison = get_client_comparisons(db, client, PERIOD_START, PERIOD_END)[0]

    for forbidden in ("rank", "position", "client_ids", "members"):
        assert forbidden not in BenchmarkComparison.model_fields
        assert forbidden not in BenchmarkComparisonPublic.model_fields
    assert comparison.period_start == PERIOD_START


def test_unapproved_snapshots_are_never_served(db):
    build_population(db, [float(n) for n in range(10, 110, 10)])
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )  # generated but never approved

    client = make_measured_client(db, ai_citability=95.0)
    presence = next(
        c
        for c in get_client_comparisons(db, client, PERIOD_START, PERIOD_END)
        if c.metric_key == "ai_presence_score"
    )
    assert presence.suppressed is True
    assert presence.suppression_reason == "no_cohort"
    assert presence.p50 is None


def test_ineligible_client_gets_a_reason_not_a_bad_score(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=95.0)
    client.benchmark_opt_out = True
    db.commit()

    comparisons = get_client_comparisons(db, client, PERIOD_START, PERIOD_END)
    assert all(c.suppressed for c in comparisons)
    assert all(c.suppression_reason == "not_eligible" for c in comparisons)
    assert all(c.p50 is None and c.percentile_band is None for c in comparisons)
    assert all(c.suppression_message for c in comparisons)


def test_metric_the_client_has_no_value_for_is_distinguished_from_poor_performance(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=None)

    presence = next(
        c
        for c in get_client_comparisons(db, client, PERIOD_START, PERIOD_END)
        if c.metric_key == "ai_presence_score"
    )
    assert presence.suppressed is True
    assert presence.suppression_reason == "no_client_value"
    assert presence.client_value is None
    assert presence.percentile_band is None


def test_every_metric_in_the_registry_gets_an_entry(db):
    from app.services.benchmark_snapshot_service import BENCHMARK_METRICS

    approved_cohort(db)
    client = make_measured_client(db, ai_citability=60.0)
    comparisons = get_client_comparisons(db, client, PERIOD_START, PERIOD_END)
    assert {c.metric_key for c in comparisons} == set(BENCHMARK_METRICS)


# --- language and public shape ------------------------------------------------


def test_cohort_label_says_comparable_clients_not_competitors(db):
    cohort = get_or_create_cohort(db, spec_for())
    label = cohort_label(cohort)

    assert "Comparable SeenBy clients" in label
    assert "competitor" not in label.lower()
    assert "Kuala Lumpur" in label


def test_public_shape_drops_cohort_key_and_exact_counts(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=95.0)
    admin = next(
        c
        for c in get_client_comparisons(db, client, PERIOD_START, PERIOD_END)
        if c.metric_key == "ai_presence_score"
    )
    public = BenchmarkComparisonPublic.from_comparison(admin)

    assert admin.cohort_key is not None
    assert "cohort_key" not in BenchmarkComparisonPublic.model_fields
    assert "eligible_member_count" not in BenchmarkComparisonPublic.model_fields
    assert "contributing_member_count" not in BenchmarkComparisonPublic.model_fields
    assert "suppression_reason" not in BenchmarkComparisonPublic.model_fields
    assert public.member_count_band == "10–19"


def test_public_shape_is_not_a_subclass_of_the_admin_shape():
    """Subclassing would mean a new admin field silently reaches share links."""
    assert not issubclass(BenchmarkComparisonPublic, BenchmarkComparison)


def test_caveat_states_description_not_guarantee(db):
    approved_cohort(db)
    client = make_measured_client(db, ai_citability=95.0)
    comparison = get_client_comparisons(db, client, PERIOD_START, PERIOD_END)[0]
    assert "not a promise" in comparison.caveat.lower()


def test_no_banned_vocabulary_in_client_facing_strings():
    """CLAUDE.md §2 — these strings are rendered to clients verbatim."""
    from app.schemas.benchmark_comparison import (
        DEFAULT_CAVEAT,
        METRIC_LABELS,
        SUPPRESSION_MESSAGES,
    )

    banned = ("cited", "uncited", "citation rate", "ranking position", "visibility gap")
    surfaces = [DEFAULT_CAVEAT, *METRIC_LABELS.values(), *SUPPRESSION_MESSAGES.values()]
    for text in surfaces:
        lowered = text.lower()
        for term in banned:
            assert term not in lowered, f"{term!r} found in client-facing string {text!r}"
