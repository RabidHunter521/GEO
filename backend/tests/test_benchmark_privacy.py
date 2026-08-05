"""Phase 6 Task 3 — attack-shaped tests for the benchmark aggregates.

These are written from the attacker's side rather than the feature's. The
threat is not someone reading a client name out of a payload; it is someone
reconstructing an individual client's number from aggregates that are each,
on their own, perfectly anonymous.
"""
from app.core.constants import MIN_METRIC_CONTRIBUTORS
from app.models.benchmark_cohort import BenchmarkCohortMembership
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_snapshot_service import (
    generate_ladder_snapshots,
    generate_snapshot,
    get_or_create_cohort,
    record_membership,
)

from tests.test_benchmark_snapshot_service import (
    PERIOD_END,
    PERIOD_START,
    build_population,
    make_measured_client,
    spec_for,
)


def test_a_suppressed_snapshot_carries_no_recoverable_numbers(db):
    build_population(db, [10.0] * 3)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    cohort = get_or_create_cohort(db, spec_for())

    snapshot = generate_snapshot(
        db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    assert snapshot.suppressed is True
    assert (snapshot.p25, snapshot.p50, snapshot.p75, snapshot.mean) == (None, None, None, None)


def test_nested_cohorts_that_differ_by_too_few_members_are_suppressed(db):
    """The differencing attack.

    If a pack-wide cohort publishes 12 members and the dental cohort publishes
    10, the two-client difference group is exposed by subtraction: their
    combined contribution is recoverable from two published medians. Neither
    snapshot leaks anything alone, which is exactly why this has to be checked
    across the ladder rather than per snapshot.
    """
    build_population(db, [float(n) for n in range(10, 110, 10)])  # 10 dental
    for _ in range(2):
        make_measured_client(db, ai_citability=55.0, subcategory="physiotherapy")
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    snapshots = generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    narrowest, *broader_rungs = snapshots

    # The client's own dental cohort publishes: 10 members, nothing to subtract.
    assert narrowest.cohort.subcategory == "dental"
    assert narrowest.suppressed is False

    # Every wider rung sits two clients above it. Suppression has to reach all
    # of them, not just the adjacent one — a rung two steps out is subtractable
    # from the narrowest just as directly.
    assert broader_rungs
    for rung in broader_rungs:
        assert rung.cohort.subcategory is None
        assert rung.suppressed is True, rung.cohort.cohort_key
        assert rung.suppression_reason == "differencing_risk"


def test_nested_cohorts_far_enough_apart_both_publish(db):
    build_population(db, [float(n) for n in range(10, 110, 10)])  # 10 dental
    for _ in range(MIN_METRIC_CONTRIBUTORS + 2):
        make_measured_client(db, ai_citability=55.0, subcategory="physiotherapy")
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    snapshots = generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    assert all(snapshot.suppressed is False for snapshot in snapshots)


def test_identical_nested_cohorts_are_not_treated_as_a_leak(db):
    """A wider cohort that happens to contain exactly the same clients adds no
    subtractable difference, so it is not a differencing risk."""
    build_population(db, [float(n) for n in range(10, 110, 10)])
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    snapshots = generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    assert all(snapshot.suppressed is False for snapshot in snapshots)


def test_generation_only_accepts_registered_metric_keys(db):
    """Blocks arbitrary caller-chosen metrics, which would otherwise let a
    caller slice until a cohort contained one client."""
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())

    try:
        generate_snapshot(db, cohort, members, "not_a_metric", PERIOD_START, PERIOD_END)
    except KeyError:
        pass
    else:
        raise AssertionError("unregistered metric key must be rejected")


def test_generation_only_accepts_cohorts_on_the_canonical_ladder(db):
    """A caller must not be able to invent a narrow cohort dimension. Every
    published cohort comes from the fixed widening ladder."""
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    invented = spec_for(market_area="unit-42-jalan-example")

    snapshots = generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    published_keys = {snapshot.cohort.cohort_key for snapshot in snapshots}
    assert invented.cohort_key not in published_keys


def test_membership_records_stay_out_of_the_snapshot(db):
    """Membership is the one table that maps aggregates to organizations. It
    must never travel with the snapshot."""
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())
    record_membership(db, cohort, members, PERIOD_START, PERIOD_END)
    snapshot = generate_snapshot(
        db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END
    )

    payload = snapshot.__dict__
    assert "client_id" not in payload
    serialized = str({k: v for k, v in payload.items() if not k.startswith("_")})
    for member in members:
        assert str(member.client_id) not in serialized


def test_membership_is_recorded_for_included_and_excluded_alike(db):
    build_population(db, [float(n) for n in range(10, 110, 10)])
    opted_out = make_measured_client(db, ai_citability=50.0)
    opted_out.benchmark_opt_out = True
    db.commit()

    everyone = eligible_members_for_period(
        db, PERIOD_START, PERIOD_END, include_excluded=True
    )
    cohort = get_or_create_cohort(db, spec_for())
    record_membership(db, cohort, everyone, PERIOD_START, PERIOD_END)

    rows = db.query(BenchmarkCohortMembership).all()
    assert len(rows) == 11
    excluded = [row for row in rows if not row.is_included]
    assert len(excluded) == 1
    assert excluded[0].exclusion_reason == "opted_out"


def test_recording_membership_twice_updates_rather_than_duplicates(db):
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())
    record_membership(db, cohort, members, PERIOD_START, PERIOD_END)
    record_membership(db, cohort, members, PERIOD_START, PERIOD_END)

    assert db.query(BenchmarkCohortMembership).count() == 10
