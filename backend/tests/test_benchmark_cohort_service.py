"""Phase 6 Task 2 — deterministic, explainable cohort eligibility.

Two rules drive every test here:

1. Missing data produces either a documented exclusion or a broader cohort.
   It never produces an invented classification. A client with no recorded
   subcategory joins the pack-wide cohort; a client with no mappable country
   is excluded with a reason. Neither is guessed at.
2. Widening is ordered and bounded. A cohort below threshold relaxes exactly
   one dimension at a time and stops rather than crossing an industry pack or
   a country to manufacture a number.
"""
import uuid
from datetime import date, datetime

import pytest

from app.core.constants import (
    BENCHMARK_EXCLUSION_REASONS,
    BENCHMARK_MIN_COVERAGE,
)
from app.schemas.benchmark_cohort import CohortSpec
from app.services.benchmark_cohort_service import (
    DEFAULT_COHORT_CONFIG,
    build_cohort_key,
    coverage_band_for,
    evaluate_client_eligibility,
    eligible_members_for_period,
    resolve_cohort,
    scale_band_for,
    widening_ladder,
)
from app.models.business_location import BusinessLocation
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.tracked_query import TrackedQuery

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)
MID_PERIOD = datetime(2026, 7, 20, 12, 0, 0)


def make_client(db, *, pack="healthcare", subcategory="dental", **overrides) -> Client:
    fields = dict(
        name="Peer Clinic",
        website=f"https://{uuid.uuid4().hex}.example",
        industry="Healthcare",
        industry_pack=pack,
        industry_subcategory=subcategory,
        country="Malaysia",
    )
    fields.update(overrides)
    client = Client(**fields)
    db.add(client)
    db.commit()
    return client


def add_locations(db, client, count, *, country="MY", city="Kuala Lumpur", active=True):
    # Only the client's very first location may be primary — business_locations
    # carries a partial unique index on (client_id) where is_primary.
    already = db.query(BusinessLocation).filter(BusinessLocation.client_id == client.id).count()
    for index in range(count):
        db.add(
            BusinessLocation(
                client_id=client.id,
                name=f"Branch {index}",
                slug=f"branch-{index}-{uuid.uuid4().hex[:6]}",
                is_primary=(already == 0 and index == 0),
                country=country,
                city=city,
                active=active,
            )
        )
    db.commit()


def add_coverage(
    db, client, query_count, *, observed_at=MID_PERIOD, prompt_version="v1", is_control=False
):
    """Give the client `query_count` tracked queries, each with one sample."""
    scan = Scan(client_id=client.id, status="completed", completed_at=observed_at)
    db.add(scan)
    db.commit()
    for index in range(query_count):
        tracked = TrackedQuery(
            client_id=client.id,
            text=f"query {index}",
            normalized_text=f"query {index} {uuid.uuid4().hex[:6]}",
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
                query_text=f"query {index}",
                tracked_query_id=tracked.id,
                sample_index=1,
                prompt_version=prompt_version,
                observed_at=observed_at,
                is_control=is_control,
            )
        )
    db.commit()


def eligible_client(db, **overrides) -> Client:
    """A client that passes every eligibility rule."""
    client = make_client(db, **overrides)
    add_locations(db, client, 1)
    add_coverage(db, client, 30)
    return client


def evaluate(db, client):
    return evaluate_client_eligibility(db, client, PERIOD_START, PERIOD_END)


# --- banding -----------------------------------------------------------------


@pytest.mark.parametrize(
    "count,expected",
    [
        (1, "single_location"),
        (2, "small_multi_location"),
        (5, "small_multi_location"),
        (6, "large_multi_location"),
        (400, "large_multi_location"),
    ],
)
def test_scale_band_boundaries(count, expected):
    assert scale_band_for(count) == expected


def test_scale_band_is_unknown_below_one_location(db):
    """Zero locations is missing data, not a single-location business."""
    assert scale_band_for(0) is None


@pytest.mark.parametrize(
    "coverage,expected",
    [
        (10, "starter"),
        (29, "starter"),
        (30, "standard"),
        (99, "standard"),
        (100, "deep"),
        (5000, "deep"),
    ],
)
def test_coverage_band_boundaries(coverage, expected):
    assert coverage_band_for(coverage) == expected


def test_coverage_below_the_starter_floor_has_no_band():
    assert coverage_band_for(BENCHMARK_MIN_COVERAGE - 1) is None


def test_bands_are_versioned_together_with_the_definition():
    assert DEFAULT_COHORT_CONFIG.definition_version
    assert DEFAULT_COHORT_CONFIG.scale_bands
    assert DEFAULT_COHORT_CONFIG.coverage_bands


# --- inclusion ---------------------------------------------------------------


def test_fully_measured_client_is_eligible(db):
    client = eligible_client(db)
    result = evaluate(db, client)

    assert result.eligible is True
    assert result.reason_codes == []
    assert result.spec.industry_pack == "healthcare"
    assert result.spec.subcategory == "dental"
    assert result.spec.country_code == "MY"
    assert result.spec.scale_band == "single_location"
    assert result.spec.coverage_band == "standard"
    assert result.measurement_coverage == 30


def test_eligibility_reports_the_measurement_it_counted(db):
    client = eligible_client(db)
    result = evaluate(db, client)

    assert result.measurement_version == "v1"
    assert result.last_observed_at == MID_PERIOD
    assert result.location_count == 1


# --- exclusions --------------------------------------------------------------


def test_opted_out_client_is_excluded(db):
    client = eligible_client(db)
    client.benchmark_opt_out = True
    db.commit()

    result = evaluate(db, client)
    assert result.eligible is False
    assert "opted_out" in result.reason_codes


def test_archived_client_is_excluded(db):
    client = eligible_client(db)
    client.archived_at = datetime(2026, 6, 1)
    db.commit()

    result = evaluate(db, client)
    assert result.eligible is False
    assert "archived" in result.reason_codes


def test_prospect_is_excluded(db):
    """Prospects are cold leads scanned for outreach, not portfolio peers —
    the same exclusion the legacy benchmark_service already makes."""
    client = eligible_client(db)
    client.is_prospect = True
    db.commit()

    result = evaluate(db, client)
    assert result.eligible is False
    assert "prospect" in result.reason_codes


def test_client_without_an_industry_pack_is_excluded_not_guessed(db):
    client = eligible_client(db, pack=None, subcategory=None)
    result = evaluate(db, client)

    assert result.eligible is False
    assert "no_industry_pack" in result.reason_codes
    assert result.spec is None


def test_client_with_unmappable_country_is_excluded(db):
    client = make_client(db, country="Somewhere")
    add_locations(db, client, 1, country=None)
    add_coverage(db, client, 30)

    result = evaluate(db, client)
    assert result.eligible is False
    assert "unmappable_country" in result.reason_codes


def test_client_without_locations_is_excluded_rather_than_assumed_single(db):
    client = make_client(db)
    add_coverage(db, client, 30)

    result = evaluate(db, client)
    assert result.eligible is False
    assert "unknown_scale" in result.reason_codes


def test_inactive_locations_do_not_count_toward_scale(db):
    client = make_client(db)
    add_locations(db, client, 1)
    add_locations(db, client, 8, active=False)
    add_coverage(db, client, 30)

    result = evaluate(db, client)
    assert result.location_count == 1
    assert result.spec.scale_band == "single_location"


def test_client_below_the_coverage_floor_is_excluded(db):
    client = make_client(db)
    add_locations(db, client, 1)
    add_coverage(db, client, BENCHMARK_MIN_COVERAGE - 1)

    result = evaluate(db, client)
    assert result.eligible is False
    assert "insufficient_coverage" in result.reason_codes


def test_control_query_samples_do_not_count_as_coverage(db):
    """Control queries are deliberately untouched benchmarks; counting them
    would let a client qualify on measurement that is never optimized."""
    client = make_client(db)
    add_locations(db, client, 1)
    add_coverage(db, client, 30, is_control=True)

    result = evaluate(db, client)
    assert result.measurement_coverage == 0
    assert "insufficient_coverage" in result.reason_codes


def test_samples_outside_the_period_do_not_count(db):
    client = make_client(db)
    add_locations(db, client, 1)
    add_coverage(db, client, 30, observed_at=datetime(2026, 5, 15, 12, 0, 0))

    result = evaluate(db, client)
    assert result.measurement_coverage == 0
    assert "insufficient_coverage" in result.reason_codes


def test_stale_measurement_is_excluded(db):
    """Coverage gathered only at the very start of a long period is not a
    current picture of the client."""
    client = make_client(db)
    add_locations(db, client, 1)
    add_coverage(db, client, 30, observed_at=datetime(2026, 7, 1, 0, 30, 0))

    stale_config = DEFAULT_COHORT_CONFIG.model_copy(update={"max_staleness_days": 7})
    result = evaluate_client_eligibility(
        db, client, PERIOD_START, PERIOD_END, config=stale_config
    )
    assert result.eligible is False
    assert "stale_measurement" in result.reason_codes


def test_unsupported_measurement_version_is_excluded(db):
    client = eligible_client(db)
    pinned = DEFAULT_COHORT_CONFIG.model_copy(
        update={"supported_measurement_versions": ("v2",)}
    )

    result = evaluate_client_eligibility(db, client, PERIOD_START, PERIOD_END, config=pinned)
    assert result.eligible is False
    assert "unsupported_measurement_version" in result.reason_codes


def test_default_config_accepts_any_measurement_version(db):
    assert DEFAULT_COHORT_CONFIG.supported_measurement_versions is None
    client = eligible_client(db)
    assert evaluate(db, client).eligible is True


def test_every_reason_code_is_declared_and_storable(db):
    """`benchmark_cohort_memberships.exclusion_reason` is String(64) with no
    database-level vocabulary. Phase 4's lesson was that a value the storage
    layer silently truncates or drops looks exactly like a working feature."""
    for code in BENCHMARK_EXCLUSION_REASONS:
        assert code == code.lower()
        assert len(code) <= 64


def test_all_exclusions_are_reported_together_not_just_the_first(db):
    client = make_client(db, country="Somewhere")
    client.benchmark_opt_out = True
    db.commit()

    result = evaluate(db, client)
    assert {"opted_out", "unmappable_country", "unknown_scale"} <= set(result.reason_codes)
    assert all(code in BENCHMARK_EXCLUSION_REASONS for code in result.reason_codes)


# --- missing dimensions widen rather than invent ------------------------------


def test_missing_subcategory_joins_the_pack_wide_cohort(db):
    client = eligible_client(db, subcategory=None)
    result = evaluate(db, client)

    assert result.eligible is True
    assert result.spec.subcategory is None


def test_missing_city_produces_a_country_wide_cohort(db):
    client = make_client(db)
    add_locations(db, client, 1, city=None)
    add_coverage(db, client, 30)

    result = evaluate(db, client)
    assert result.eligible is True
    assert result.spec.market_area is None


def test_market_area_is_normalized_from_the_primary_location(db):
    client = eligible_client(db)
    assert evaluate(db, client).spec.market_area == "kuala-lumpur"


# --- cohort key --------------------------------------------------------------


def test_cohort_key_is_deterministic(db):
    client = eligible_client(db)
    first = evaluate(db, client).spec
    second = evaluate(db, client).spec
    assert first.cohort_key == second.cohort_key
    assert first.cohort_key == build_cohort_key(first)


def test_cohort_key_distinguishes_absent_from_present_dimensions(db):
    narrow = CohortSpec(
        industry_pack="healthcare",
        subcategory="dental",
        country_code="MY",
        market_area="kuala-lumpur",
        scale_band="single_location",
        coverage_band="standard",
        period_type="month",
        definition_version="v1",
    )
    broad = narrow.model_copy(update={"subcategory": None, "market_area": None})
    assert narrow.cohort_key != broad.cohort_key


# --- widening ladder ----------------------------------------------------------


def _spec(**overrides) -> CohortSpec:
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


def test_widening_relaxes_one_dimension_at_a_time_in_the_documented_order(db):
    ladder = widening_ladder(_spec())

    assert ladder[0] == _spec()
    assert ladder[1].subcategory is None and ladder[1].market_area == "kuala-lumpur"
    assert ladder[2].subcategory is None and ladder[2].market_area is None
    assert ladder[3].scale_band == "single_or_small_location"


def test_widening_never_crosses_pack_or_country(db):
    for spec in widening_ladder(_spec()):
        assert spec.industry_pack == "healthcare"
        assert spec.country_code == "MY"


def test_widening_never_relaxes_the_coverage_band(db):
    """Coverage is what makes two clients comparable at all; merging a starter
    client into a deep cohort would compare 10 queries against 100."""
    for spec in widening_ladder(_spec()):
        assert spec.coverage_band == "standard"


def test_widening_terminates(db):
    ladder = widening_ladder(_spec())
    assert len(ladder) == len(set(spec.cohort_key for spec in ladder))
    assert len(ladder) <= 4


def test_large_multi_location_does_not_widen_into_the_small_band(db):
    ladder = widening_ladder(_spec(scale_band="large_multi_location"))
    assert all(spec.scale_band == "large_multi_location" for spec in ladder)


# --- resolution against real membership ---------------------------------------


def _make_cohort_population(db, count, **overrides):
    return [eligible_client(db, **overrides) for _ in range(count)]


def test_resolve_returns_the_narrowest_cohort_that_meets_the_minimum(db):
    _make_cohort_population(db, 10)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    assert len(members) == 10

    resolved = resolve_cohort(_spec(), members, min_member_count=10)
    assert resolved is not None
    assert resolved.subcategory == "dental"
    assert resolved.market_area == "kuala-lumpur"


def test_resolve_widens_when_the_narrow_cohort_is_short(db):
    _make_cohort_population(db, 6, subcategory="dental")
    _make_cohort_population(db, 6, subcategory="physiotherapy")
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    resolved = resolve_cohort(_spec(), members, min_member_count=10)
    assert resolved is not None
    assert resolved.subcategory is None
    assert resolved.market_area == "kuala-lumpur"


def test_resolve_suppresses_rather_than_crossing_a_pack_boundary(db):
    _make_cohort_population(db, 4, pack="healthcare")
    _make_cohort_population(db, 20, pack="fnb", subcategory=None)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    assert resolve_cohort(_spec(), members, min_member_count=10) is None


def test_resolve_suppresses_rather_than_crossing_a_country_boundary(db):
    for _ in range(4):
        client = make_client(db)
        add_locations(db, client, 1, country="MY")
        add_coverage(db, client, 30)
    for _ in range(20):
        client = make_client(db)
        add_locations(db, client, 1, country="SG", city="Singapore")
        add_coverage(db, client, 30)
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)

    assert resolve_cohort(_spec(), members, min_member_count=10) is None


def test_excluded_clients_are_returned_with_their_reasons_for_audit(db):
    eligible_client(db)
    opted_out = eligible_client(db)
    opted_out.benchmark_opt_out = True
    db.commit()

    included = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    assert len(included) == 1

    everyone = eligible_members_for_period(
        db, PERIOD_START, PERIOD_END, include_excluded=True
    )
    assert len(everyone) == 2
    excluded = [row for row in everyone if not row.eligible]
    assert excluded[0].reason_codes == ["opted_out"]
