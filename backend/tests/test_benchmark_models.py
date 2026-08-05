"""Phase 6 Task 1 — benchmark cohort, membership, and snapshot storage.

These are the privacy invariants of the entire data moat, so they are enforced
in the schema rather than only in the service that writes them. A suppressed
snapshot that still carries a p50, or an exclusion with no recorded reason, is
the exact defect that turns "privacy-safe benchmark" into a leak, and it should
be the database that refuses it — not a code path someone can forget to call.
"""
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.benchmark_cohort import BenchmarkCohort, BenchmarkCohortMembership
from app.models.benchmark_snapshot import (
    ApprovedSnapshotImmutableError,
    BenchmarkSnapshot,
)
from app.models.client import Client

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)


def make_client(db, name="Peer Clinic") -> Client:
    client = Client(name=name, website=f"https://{uuid.uuid4().hex}.example", industry="Healthcare")
    db.add(client)
    db.commit()
    return client


def make_cohort(db, **overrides) -> BenchmarkCohort:
    defaults = dict(
        cohort_key="healthcare|MY|single_location|standard|month",
        definition_version="v1",
        industry_pack="healthcare",
        subcategory=None,
        country_code="MY",
        market_area=None,
        scale_band="single_location",
        coverage_band="standard",
        period_type="month",
        min_member_count=10,
        is_active=True,
    )
    defaults.update(overrides)
    cohort = BenchmarkCohort(**defaults)
    db.add(cohort)
    db.commit()
    return cohort


def make_snapshot(db, cohort, **overrides) -> BenchmarkSnapshot:
    defaults = dict(
        cohort_id=cohort.id,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        metric_key="ai_presence_score",
        calculation_version="v1",
        eligible_member_count=12,
        contributing_member_count=11,
        p25=40,
        p50=55,
        p75=70,
        mean=56,
        suppressed=False,
    )
    defaults.update(overrides)
    snapshot = BenchmarkSnapshot(**defaults)
    db.add(snapshot)
    db.commit()
    return snapshot


# --- cohort definition -------------------------------------------------------


def test_cohort_key_is_unique_per_definition_version(db):
    make_cohort(db)
    make_cohort(db, definition_version="v2")  # same key, new version is allowed

    db.add(
        BenchmarkCohort(
            cohort_key="healthcare|MY|single_location|standard|month",
            definition_version="v1",
            industry_pack="healthcare",
            country_code="MY",
            scale_band="single_location",
            coverage_band="standard",
            period_type="month",
            min_member_count=10,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_min_member_count_cannot_be_configured_below_ten(db):
    """The plan allows the minimum to be configured upward only. Downward is
    the one change that would silently convert every suppression into a
    publishable number, so the floor is a database constraint."""
    with pytest.raises(IntegrityError):
        make_cohort(db, min_member_count=9)


def test_min_member_count_may_be_raised(db):
    cohort = make_cohort(db, min_member_count=25)
    assert cohort.min_member_count == 25


# --- membership --------------------------------------------------------------


def test_membership_is_unique_per_cohort_client_and_evaluation_period(db):
    cohort = make_cohort(db)
    client = make_client(db)
    for _ in range(2):
        db.add(
            BenchmarkCohortMembership(
                cohort_id=cohort.id,
                client_id=client.id,
                evaluation_period_start=PERIOD_START,
                evaluation_period_end=PERIOD_END,
                is_included=True,
                measurement_coverage=42,
            )
        )
    with pytest.raises(IntegrityError):
        db.commit()


def test_exclusion_must_record_a_reason(db):
    """An unexplainable exclusion is indistinguishable from a bug."""
    cohort = make_cohort(db)
    client = make_client(db)
    db.add(
        BenchmarkCohortMembership(
            cohort_id=cohort.id,
            client_id=client.id,
            evaluation_period_start=PERIOD_START,
            evaluation_period_end=PERIOD_END,
            is_included=False,
            exclusion_reason=None,
            measurement_coverage=0,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_inclusion_must_not_record_an_exclusion_reason(db):
    cohort = make_cohort(db)
    client = make_client(db)
    db.add(
        BenchmarkCohortMembership(
            cohort_id=cohort.id,
            client_id=client.id,
            evaluation_period_start=PERIOD_START,
            evaluation_period_end=PERIOD_END,
            is_included=True,
            exclusion_reason="opted_out",
            measurement_coverage=42,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_excluded_membership_with_reason_is_accepted(db):
    cohort = make_cohort(db)
    client = make_client(db)
    membership = BenchmarkCohortMembership(
        cohort_id=cohort.id,
        client_id=client.id,
        evaluation_period_start=PERIOD_START,
        evaluation_period_end=PERIOD_END,
        is_included=False,
        exclusion_reason="opted_out",
        measurement_coverage=0,
    )
    db.add(membership)
    db.commit()
    assert membership.evaluated_at is not None


# --- snapshot invariants -----------------------------------------------------


def test_snapshot_is_unique_per_cohort_period_metric_and_calculation_version(db):
    cohort = make_cohort(db)
    make_snapshot(db, cohort)
    db.add(
        BenchmarkSnapshot(
            cohort_id=cohort.id,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            metric_key="ai_presence_score",
            calculation_version="v1",
            eligible_member_count=12,
            contributing_member_count=11,
            p25=41,
            p50=56,
            p75=71,
            mean=57,
            suppressed=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_new_calculation_version_is_a_new_snapshot_not_a_mutation(db):
    cohort = make_cohort(db)
    make_snapshot(db, cohort)
    corrected = make_snapshot(db, cohort, calculation_version="v2", p50=58)
    assert corrected.id is not None


def test_suppressed_snapshot_must_not_carry_aggregate_values(db):
    """The single most dangerous row in Phase 6: suppressed but populated."""
    cohort = make_cohort(db)
    with pytest.raises(IntegrityError):
        make_snapshot(db, cohort, suppressed=True, contributing_member_count=3)


def test_suppressed_snapshot_with_null_aggregates_is_accepted(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(
        db,
        cohort,
        suppressed=True,
        contributing_member_count=3,
        p25=None,
        p50=None,
        p75=None,
        mean=None,
    )
    assert snapshot.suppressed is True
    assert snapshot.p50 is None


def test_unsuppressed_snapshot_must_carry_aggregate_values(db):
    cohort = make_cohort(db)
    with pytest.raises(IntegrityError):
        make_snapshot(db, cohort, suppressed=False, p50=None)


def test_contributing_members_cannot_exceed_eligible_members(db):
    cohort = make_cohort(db)
    with pytest.raises(IntegrityError):
        make_snapshot(db, cohort, eligible_member_count=10, contributing_member_count=11)


def test_percentiles_must_be_ordered(db):
    cohort = make_cohort(db)
    with pytest.raises(IntegrityError):
        make_snapshot(db, cohort, p25=70, p50=55, p75=40)


def test_period_start_must_not_follow_period_end(db):
    cohort = make_cohort(db)
    with pytest.raises(IntegrityError):
        make_snapshot(db, cohort, period_start=PERIOD_END, period_end=PERIOD_START)


# --- immutability of approved snapshots --------------------------------------


def test_unapproved_snapshot_can_be_corrected(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    snapshot.p50 = 60
    db.commit()
    assert snapshot.p50 == 60


def test_snapshot_can_transition_into_approved(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    snapshot.approved_at = datetime(2026, 8, 1, 9, 0, 0)
    db.commit()
    assert snapshot.approved_at is not None


def test_approved_snapshot_rejects_any_further_update(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    snapshot.approved_at = datetime(2026, 8, 1, 9, 0, 0)
    db.commit()

    snapshot.p50 = 99
    with pytest.raises(ApprovedSnapshotImmutableError):
        db.commit()


def test_approved_snapshot_cannot_be_unapproved(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    snapshot.approved_at = datetime(2026, 8, 1, 9, 0, 0)
    db.commit()

    snapshot.approved_at = None
    with pytest.raises(ApprovedSnapshotImmutableError):
        db.commit()


def test_approved_snapshot_cannot_be_deleted(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    snapshot.approved_at = datetime(2026, 8, 1, 9, 0, 0)
    db.commit()

    db.delete(snapshot)
    with pytest.raises(ApprovedSnapshotImmutableError):
        db.commit()


def test_unapproved_snapshot_can_be_deleted(db):
    cohort = make_cohort(db)
    snapshot = make_snapshot(db, cohort)
    db.delete(snapshot)
    db.commit()
    assert db.query(BenchmarkSnapshot).count() == 0


# --- client opt-out ----------------------------------------------------------


def test_clients_default_to_participating_in_benchmarks(db):
    client = make_client(db)
    assert client.benchmark_opt_out is False


def test_client_can_opt_out_of_benchmarks(db):
    client = make_client(db)
    client.benchmark_opt_out = True
    db.commit()
    assert client.benchmark_opt_out is True
