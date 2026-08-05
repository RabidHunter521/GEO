"""Phase 6 Task 3 — privacy-safe snapshot generation.

Aggregation correctness lives here; the attack-shaped tests live in
test_benchmark_privacy.py.
"""
import uuid
from datetime import date, datetime

import pytest

from app.core.constants import MIN_METRIC_CONTRIBUTORS
from app.models.benchmark_snapshot import BenchmarkSnapshot
from app.models.business_location import BusinessLocation
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.tracked_query import TrackedQuery
from app.schemas.benchmark_cohort import CohortSpec
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_snapshot_service import (
    BENCHMARK_METRICS,
    clip_value,
    collect_metric_values,
    generate_snapshot,
    get_or_create_cohort,
    percentile,
)

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)
MID_PERIOD = datetime(2026, 7, 20, 12, 0, 0)


def make_measured_client(db, *, ai_citability=50.0, subcategory="dental") -> Client:
    client = Client(
        name="Peer Clinic",
        website=f"https://{uuid.uuid4().hex}.example",
        industry="Healthcare",
        industry_pack="healthcare",
        industry_subcategory=subcategory,
        country="Malaysia",
    )
    db.add(client)
    db.commit()

    db.add(
        BusinessLocation(
            client_id=client.id,
            name="Main",
            slug=f"main-{uuid.uuid4().hex[:6]}",
            is_primary=True,
            country="MY",
            city="Kuala Lumpur",
            active=True,
        )
    )
    scan = Scan(client_id=client.id, status="completed", completed_at=MID_PERIOD)
    db.add(scan)
    db.commit()

    for index in range(30):
        tracked = TrackedQuery(
            client_id=client.id,
            text=f"q{index}",
            normalized_text=f"q{index}-{uuid.uuid4().hex[:6]}",
            source="admin",
            intent="brand",
        )
        db.add(tracked)
        db.commit()
        db.add(
            ScanQueryResult(
                scan_id=scan.id,
                platform="chatgpt",
                category="brand",
                query_text=f"q{index}",
                tracked_query_id=tracked.id,
                sample_index=1,
                observed_at=MID_PERIOD,
                response_text="answer",
                brand_detected=True,
            )
        )
    if ai_citability is not None:
        db.add(
            GeoScore(
                client_id=client.id,
                scan_id=scan.id,
                ai_citability=ai_citability,
                overall_score=ai_citability,
                computed_at=MID_PERIOD,
            )
        )
    db.commit()
    return client


def spec_for(**overrides) -> CohortSpec:
    fields = dict(
        industry_pack="healthcare",
        subcategory="dental",
        country_code="MY",
        market_area="kuala-lumpur",
        scale_band="single_location",
        coverage_band="standard",
        period_type="month",
        definition_version="v1",
    )
    fields.update(overrides)
    return CohortSpec(**fields)


def build_population(db, scores):
    for score in scores:
        make_measured_client(db, ai_citability=score)
    return eligible_members_for_period(db, PERIOD_START, PERIOD_END)


# --- pure helpers -------------------------------------------------------------


@pytest.mark.parametrize(
    "values,q,expected",
    [
        ([10, 20, 30, 40], 0.5, 25.0),
        ([10, 20, 30, 40, 50], 0.5, 30.0),
        ([10, 20, 30, 40, 50], 0.25, 20.0),
        ([10, 20, 30, 40, 50], 0.75, 40.0),
        ([7], 0.5, 7.0),
    ],
)
def test_percentile_uses_linear_interpolation(values, q, expected):
    assert percentile(sorted(values), q) == pytest.approx(expected)


def test_percentile_of_empty_series_is_none():
    assert percentile([], 0.5) is None


@pytest.mark.parametrize(
    "value,bounds,expected",
    [
        (150, (0, 100), 100.0),
        (-4, (0, 100), 0.0),
        (0.5, (0, 1), 0.5),
        (2.0, (0, 1), 1.0),
    ],
)
def test_clip_bounds_outliers_rather_than_dropping_them(value, bounds, expected):
    assert clip_value(value, bounds) == pytest.approx(expected)


def test_metric_registry_declares_a_complete_definition_for_every_metric():
    for key, metric in BENCHMARK_METRICS.items():
        assert metric.key == key
        assert metric.unit
        assert metric.calculation_version
        assert metric.clip[0] < metric.clip[1]
        assert metric.min_coverage >= 0
        assert callable(metric.extractor)


def test_registry_excludes_estimated_revenue():
    """The plan bars benchmarking modeled money in the first release: an
    estimate compared against other estimates reads as a measurement."""
    for key in BENCHMARK_METRICS:
        assert "revenue" not in key
        assert "estimated" not in key


# --- value collection ---------------------------------------------------------


def test_collect_reads_one_value_per_contributing_client(db):
    members = build_population(db, [40.0, 60.0, 80.0])
    values = collect_metric_values(db, BENCHMARK_METRICS["ai_presence_score"], members, PERIOD_START, PERIOD_END)

    assert sorted(values.values()) == [40.0, 60.0, 80.0]


def test_clients_without_the_metric_are_absent_not_zero(db):
    """A missing value must never enter the series as a zero — it would drag
    every percentile down and read as terrible performance."""
    build_population(db, [40.0, 60.0])
    make_measured_client(db, ai_citability=None)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    values = collect_metric_values(db, BENCHMARK_METRICS["ai_presence_score"], members, PERIOD_START, PERIOD_END)
    assert len(members) == 3
    assert len(values) == 2
    assert 0.0 not in values.values()


def test_collected_values_are_clipped_to_the_registry_bounds(db):
    members = build_population(db, [140.0, 60.0])
    values = collect_metric_values(db, BENCHMARK_METRICS["ai_presence_score"], members, PERIOD_START, PERIOD_END)
    assert max(values.values()) == 100.0


# --- snapshot generation ------------------------------------------------------


def test_snapshot_records_percentiles_and_lineage(db):
    members = build_population(db, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    cohort = get_or_create_cohort(db, spec_for())

    snapshot = generate_snapshot(
        db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END
    )

    assert snapshot.suppressed is False
    assert snapshot.eligible_member_count == 10
    assert snapshot.contributing_member_count == 10
    assert float(snapshot.p50) == pytest.approx(55.0)
    assert float(snapshot.mean) == pytest.approx(55.0)
    assert snapshot.calculation_version == BENCHMARK_METRICS["ai_presence_score"].calculation_version
    assert snapshot.period_start == PERIOD_START


def test_snapshot_is_suppressed_below_the_cohort_minimum(db):
    members = build_population(db, [10.0] * 9)
    cohort = get_or_create_cohort(db, spec_for())

    snapshot = generate_snapshot(
        db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    assert snapshot.suppressed is True
    assert snapshot.suppression_reason == "cohort_below_minimum"
    assert snapshot.p50 is None


def test_snapshot_is_suppressed_when_too_few_members_contribute(db):
    """An eligible cohort is not enough: the metric itself needs contributors."""
    build_population(db, [10.0] * (MIN_METRIC_CONTRIBUTORS - 1))
    for _ in range(8):
        make_measured_client(db, ai_citability=None)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    cohort = get_or_create_cohort(db, spec_for())

    snapshot = generate_snapshot(
        db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END
    )
    assert snapshot.eligible_member_count >= cohort.min_member_count
    assert snapshot.suppressed is True
    assert snapshot.suppression_reason == "insufficient_contributors"
    assert snapshot.p50 is None


def test_regenerating_the_same_version_is_idempotent(db):
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())

    first = generate_snapshot(db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END)
    second = generate_snapshot(db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END)

    assert first.id == second.id
    assert db.query(BenchmarkSnapshot).count() == 1


def test_regeneration_never_touches_an_approved_snapshot(db):
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())
    snapshot = generate_snapshot(db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END)
    snapshot.approved_at = datetime(2026, 8, 1, 9, 0, 0)
    db.commit()
    approved_median = float(snapshot.p50)

    make_measured_client(db, ai_citability=5.0)
    changed_members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    again = generate_snapshot(
        db, cohort, changed_members, "ai_presence_score", PERIOD_START, PERIOD_END
    )

    assert again.id == snapshot.id
    assert float(again.p50) == pytest.approx(approved_median)


def test_a_new_calculation_version_writes_a_second_row(db):
    members = build_population(db, [float(n) for n in range(10, 110, 10)])
    cohort = get_or_create_cohort(db, spec_for())
    generate_snapshot(db, cohort, members, "ai_presence_score", PERIOD_START, PERIOD_END)

    generate_snapshot(
        db,
        cohort,
        members,
        "ai_presence_score",
        PERIOD_START,
        PERIOD_END,
        calculation_version="v2",
    )
    assert db.query(BenchmarkSnapshot).count() == 2


def test_cohort_rows_are_reused_not_duplicated(db):
    first = get_or_create_cohort(db, spec_for())
    second = get_or_create_cohort(db, spec_for())
    assert first.id == second.id


def test_cohort_is_created_with_the_configured_floor(db):
    cohort = get_or_create_cohort(db, spec_for())
    assert cohort.min_member_count >= 10
    assert cohort.cohort_key == spec_for().cohort_key
