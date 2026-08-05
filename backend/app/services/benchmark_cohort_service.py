# backend/app/services/benchmark_cohort_service.py
"""Deterministic, explainable cohort eligibility for the benchmark engine.

Two rules govern everything here.

**Missing data widens or excludes; it never invents.** A client with no
recorded subcategory joins the pack-wide cohort — that is a real, broader
population. A client with no mappable country is excluded with a reason code,
because putting them in an arbitrary country's cohort would corrupt everyone
else's number. The line between the two is whether the wider bucket is still
true of the client.

**Widening is ordered and bounded.** When a cohort is short of its minimum, one
dimension relaxes at a time in a documented order, and the ladder stops rather
than crossing an industry pack or a country. A benchmark that reached its
threshold by comparing a Malaysian dental clinic to a Singaporean restaurant
would be a number with no meaning, which is worse than no number at all.

This module is pure with respect to the database in the parts that matter:
banding, key construction, the widening ladder, and cohort resolution are all
plain functions over values, so they are testable without fixtures. Only
`evaluate_client_eligibility` and `eligible_members_for_period` touch a session.
"""
import re
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import (
    BENCHMARK_COVERAGE_BANDS,
    BENCHMARK_SCALE_BANDS,
    COUNTRY_NAME_TO_ISO,
)
from app.models.business_location import BusinessLocation
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult
from app.models.tracked_query import TrackedQuery
from app.schemas.benchmark_cohort import (
    CohortDefinitionConfig,
    CohortEligibility,
    CohortSpec,
)

DEFAULT_COHORT_CONFIG = CohortDefinitionConfig()

_NON_SLUG = re.compile(r"[^a-z0-9]+")


# --- banding ------------------------------------------------------------------


def scale_band_for(location_count: int, config: CohortDefinitionConfig | None = None) -> str | None:
    """Band a client by active location count.

    Returns None below one location. Zero locations is missing data, not a
    single-location business, and treating it as one would quietly file every
    un-onboarded client into the largest cohort.
    """
    bands = (config or DEFAULT_COHORT_CONFIG).scale_bands or BENCHMARK_SCALE_BANDS
    for band, (low, high) in bands.items():
        if low <= location_count < high:
            return band
    return None


def coverage_band_for(coverage: int, config: CohortDefinitionConfig | None = None) -> str | None:
    """Band a client by how many distinct tracked queries were sampled.

    Returns None below the starter floor: a client measured on 4 queries has no
    band, because nothing in the cohort is comparable to that little evidence.
    """
    bands = (config or DEFAULT_COHORT_CONFIG).coverage_bands or BENCHMARK_COVERAGE_BANDS
    for band, (low, high) in bands.items():
        if low <= coverage <= high:
            return band
    return None


def normalize_market_area(city: str | None) -> str | None:
    """Slugify a city into a stable market-area token, or None if absent."""
    if not city or not city.strip():
        return None
    slug = _NON_SLUG.sub("-", city.strip().lower()).strip("-")
    return slug or None


def normalize_country_code(client: Client, locations: list[BusinessLocation]) -> str | None:
    """Resolve an ISO-3166 alpha-2 code, preferring location data.

    `business_locations.country` is already alpha-2 and admin-maintained;
    `clients.country` is free text and only rescues clients whose locations
    predate that column. An unrecognized value returns None, which the caller
    turns into an exclusion — the plan forbids guessing a country to fill a
    cohort, since a wrong guess pollutes a real country's aggregate.
    """
    for location in locations:
        if location.country and len(location.country.strip()) == 2:
            return location.country.strip().upper()
    if client.country:
        return COUNTRY_NAME_TO_ISO.get(client.country.strip().lower())
    return None


def build_cohort_key(spec: CohortSpec) -> str:
    return spec.cohort_key


# --- eligibility --------------------------------------------------------------


def _period_bounds(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    """Inclusive date period -> half-open datetime window."""
    return (
        datetime.combine(period_start, time.min),
        datetime.combine(period_end, time.max),
    )


def _measurement_for_period(
    db: Session, client_id: uuid.UUID, period_start: date, period_end: date
) -> tuple[int, str | None, datetime | None]:
    """Distinct non-control tracked queries sampled in the period.

    Counts tracked queries, not rows: five repeated samples of one query is
    still one query's worth of coverage, and counting rows would let repeat
    sampling inflate a client into a higher band without measuring anything new.
    Control queries are excluded because they are deliberately never optimized;
    qualifying on them would mean qualifying on work the client never receives.
    """
    window_start, window_end = _period_bounds(period_start, period_end)
    row = (
        db.query(
            func.count(func.distinct(ScanQueryResult.tracked_query_id)),
            func.max(ScanQueryResult.observed_at),
        )
        .join(TrackedQuery, TrackedQuery.id == ScanQueryResult.tracked_query_id)
        .filter(
            TrackedQuery.client_id == client_id,
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.observed_at >= window_start,
            ScanQueryResult.observed_at <= window_end,
        )
        .one()
    )
    coverage = int(row[0] or 0)
    last_observed_at = row[1]

    version = None
    if coverage:
        version = (
            db.query(ScanQueryResult.prompt_version)
            .join(TrackedQuery, TrackedQuery.id == ScanQueryResult.tracked_query_id)
            .filter(
                TrackedQuery.client_id == client_id,
                ScanQueryResult.is_control.is_(False),
                ScanQueryResult.observed_at >= window_start,
                ScanQueryResult.observed_at <= window_end,
            )
            .order_by(ScanQueryResult.observed_at.desc())
            .limit(1)
            .scalar()
        )
    return coverage, version, last_observed_at


def evaluate_client_eligibility(
    db: Session,
    client: Client,
    period_start: date,
    period_end: date,
    config: CohortDefinitionConfig | None = None,
    period_type: str = "month",
) -> CohortEligibility:
    """Decide whether one client counts toward a cohort in one period.

    Every failing rule is collected, not just the first: an operator repairing
    a client's exclusion should see the whole list rather than rediscovering
    one reason per run.
    """
    config = config or DEFAULT_COHORT_CONFIG
    reasons: list[str] = []

    if client.benchmark_opt_out:
        reasons.append("opted_out")
    if client.archived_at is not None:
        reasons.append("archived")
    if client.is_prospect:
        reasons.append("prospect")
    if not client.industry_pack:
        reasons.append("no_industry_pack")

    locations = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.client_id == client.id,
            BusinessLocation.active.is_(True),
        )
        .order_by(BusinessLocation.is_primary.desc(), BusinessLocation.created_at.asc())
        .all()
    )
    location_count = len(locations)

    country_code = normalize_country_code(client, locations)
    if country_code is None:
        reasons.append("unmappable_country")

    scale_band = scale_band_for(location_count, config)
    if scale_band is None:
        reasons.append("unknown_scale")

    coverage, measurement_version, last_observed_at = _measurement_for_period(
        db, client.id, period_start, period_end
    )
    coverage_band = coverage_band_for(coverage, config)
    if coverage_band is None:
        reasons.append("insufficient_coverage")
    else:
        staleness_floor = datetime.combine(
            period_end - timedelta(days=config.max_staleness_days), time.min
        )
        if last_observed_at is not None and last_observed_at < staleness_floor:
            reasons.append("stale_measurement")

        supported = config.supported_measurement_versions
        if supported is not None and measurement_version not in supported:
            reasons.append("unsupported_measurement_version")

    if reasons:
        return CohortEligibility(
            client_id=client.id,
            eligible=False,
            reason_codes=reasons,
            spec=None,
            location_count=location_count,
            measurement_coverage=coverage,
            measurement_version=measurement_version,
            last_observed_at=last_observed_at,
        )

    spec = CohortSpec(
        industry_pack=client.industry_pack,
        # Absent is genuinely broader, not unknown-and-guessed: the client
        # simply joins the pack-wide population.
        subcategory=client.industry_subcategory or None,
        country_code=country_code,
        market_area=normalize_market_area(locations[0].city if locations else None),
        scale_band=scale_band,
        coverage_band=coverage_band,
        period_type=period_type,
        definition_version=config.definition_version,
    )
    return CohortEligibility(
        client_id=client.id,
        eligible=True,
        reason_codes=[],
        spec=spec,
        location_count=location_count,
        measurement_coverage=coverage,
        measurement_version=measurement_version,
        last_observed_at=last_observed_at,
    )


def eligible_members_for_period(
    db: Session,
    period_start: date,
    period_end: date,
    config: CohortDefinitionConfig | None = None,
    period_type: str = "month",
    include_excluded: bool = False,
) -> list[CohortEligibility]:
    """Evaluate every client for a period.

    `include_excluded` returns the exclusions too, with their reasons, so the
    membership table can record why each non-member was left out. Callers that
    only want the population for aggregation take the default.
    """
    clients = db.query(Client).order_by(Client.created_at.asc()).all()
    results = [
        evaluate_client_eligibility(
            db, client, period_start, period_end, config=config, period_type=period_type
        )
        for client in clients
    ]
    if include_excluded:
        return results
    return [result for result in results if result.eligible]


# --- widening -----------------------------------------------------------------


def widening_ladder(
    spec: CohortSpec, config: CohortDefinitionConfig | None = None
) -> list[CohortSpec]:
    """Progressively broader cohorts, narrowest first.

    The documented order, one dimension per rung:

    1. the spec as given;
    2. drop subcategory (pack-wide);
    3. drop market area (country-wide);
    4. merge adjacent scale bands.

    Industry pack, country, and coverage band never relax. The first two are
    the plan's hard boundaries. Coverage stays fixed because it is what makes
    two clients comparable at all — merging a starter client into a deep cohort
    would compare a 10-query picture against a 100-query one and call the
    difference performance.
    """
    config = config or DEFAULT_COHORT_CONFIG
    ladder = [spec]

    if spec.subcategory is not None:
        ladder.append(ladder[-1].model_copy(update={"subcategory": None}))
    if spec.market_area is not None:
        ladder.append(ladder[-1].model_copy(update={"market_area": None}))

    merged = config.merged_scale_bands.get(spec.scale_band, spec.scale_band)
    if merged != spec.scale_band:
        ladder.append(ladder[-1].model_copy(update={"scale_band": merged}))

    return ladder


def _matches(member_spec: CohortSpec, target: CohortSpec, config: CohortDefinitionConfig) -> bool:
    """Does an eligible member belong to `target`?

    A None dimension on the target means "any value" — that is what dropping
    the dimension widened it to. A merged scale band matches every fine band
    that maps into it.
    """
    if member_spec.industry_pack != target.industry_pack:
        return False
    if member_spec.country_code != target.country_code:
        return False
    if member_spec.coverage_band != target.coverage_band:
        return False
    if member_spec.period_type != target.period_type:
        return False
    if target.subcategory is not None and member_spec.subcategory != target.subcategory:
        return False
    if target.market_area is not None and member_spec.market_area != target.market_area:
        return False

    if member_spec.scale_band == target.scale_band:
        return True
    return config.merged_scale_bands.get(member_spec.scale_band) == target.scale_band


def count_members(
    target: CohortSpec,
    members: list[CohortEligibility],
    config: CohortDefinitionConfig | None = None,
) -> int:
    config = config or DEFAULT_COHORT_CONFIG
    return sum(
        1 for member in members if member.spec is not None and _matches(member.spec, target, config)
    )


def resolve_cohort(
    spec: CohortSpec,
    members: list[CohortEligibility],
    min_member_count: int,
    config: CohortDefinitionConfig | None = None,
) -> CohortSpec | None:
    """The narrowest cohort on the ladder that reaches `min_member_count`.

    None means suppress. That is a correct, expected outcome — the ladder is
    deliberately short and refuses to cross a pack or a country, so a small
    market simply has no publishable cohort until it grows.
    """
    config = config or DEFAULT_COHORT_CONFIG
    for candidate in widening_ladder(spec, config):
        if count_members(candidate, members, config) >= min_member_count:
            return candidate
    return None
