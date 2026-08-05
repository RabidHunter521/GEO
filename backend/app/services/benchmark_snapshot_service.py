# backend/app/services/benchmark_snapshot_service.py
"""Privacy-safe aggregation of eligible clients into immutable snapshots.

Three suppression rules stack, and all three have to hold before a number is
written:

1. **Cohort minimum** — fewer than `cohort.min_member_count` eligible
   organizations and nothing is published at all.
2. **Contributor minimum** — an eligible cohort still suppresses a metric when
   fewer than `MIN_METRIC_CONTRIBUTORS` members actually have a value. A
   12-member cohort where 3 clients have a stability score must not publish
   those 3 people's median.
3. **Differencing** — two nested cohorts whose contributor counts differ by
   fewer than `MIN_METRIC_CONTRIBUTORS` expose the difference group by
   subtraction. Neither snapshot leaks anything on its own, which is precisely
   why this is checked across a ladder rather than per row.

Values are clipped into the metric's declared range rather than dropped: an
outlier is real data about a real client, and discarding it would bias the
median, while letting an out-of-range value through would corrupt it.

A missing value is never a zero. Absence is absence — a client with no
stability reading is not a client with terrible stability, and folding one into
the other is the fastest way to publish a defamatory number about a cohort.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable

from sqlalchemy.orm import Session

from app.core.constants import (
    MIN_COHORT_MEMBER_FLOOR,
    MIN_METRIC_CONTRIBUTORS,
)
from app.core.time import utcnow
from app.models.benchmark_cohort import BenchmarkCohort, BenchmarkCohortMembership
from app.models.benchmark_snapshot import BenchmarkSnapshot
from app.models.geo_score import GeoScore
from app.models.outcome_action import OutcomeAction
from app.models.scan_query_result import ScanQueryResult
from app.models.share_of_source_snapshot import ShareOfSourceSnapshot
from app.models.tracked_query import TrackedQuery
from app.schemas.benchmark_cohort import CohortEligibility, CohortSpec
from app.services.benchmark_cohort_service import widening_ladder
from app.services.query_stability_service import calculate_portfolio_stability

logger = logging.getLogger(__name__)

SNAPSHOT_CALCULATION_VERSION = "v1"


def _window(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    return datetime.combine(period_start, time.min), datetime.combine(period_end, time.max)


# --- metric extractors --------------------------------------------------------
# Each returns one client's value for the period, or None when the client has
# no reading. None must never be coerced to 0.


def _ai_presence_score(db: Session, client_id: uuid.UUID, start: date, end: date) -> float | None:
    """AI Citability from the client's most recent score inside the period."""
    lo, hi = _window(start, end)
    row = (
        db.query(GeoScore.ai_citability)
        .filter(
            GeoScore.client_id == client_id,
            GeoScore.computed_at >= lo,
            GeoScore.computed_at <= hi,
        )
        .order_by(GeoScore.computed_at.desc())
        .limit(1)
        .scalar()
    )
    return float(row) if row is not None else None


def _answer_stability_score(
    db: Session, client_id: uuid.UUID, start: date, end: date
) -> float | None:
    """Mean stability across the client's tracked queries that have a score.

    Queries in the `insufficient` state carry a None score and are skipped
    rather than counted as zero — not enough samples is not instability.
    """
    lo, hi = _window(start, end)
    stabilities = calculate_portfolio_stability(client_id, db, period_start=lo, period_end=hi)
    scores = [item.score for item in stabilities if item.score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _accuracy_rate(db: Session, client_id: uuid.UUID, start: date, end: date) -> float | None:
    """Share of answered, non-control samples with no accuracy issue flagged."""
    lo, hi = _window(start, end)
    rows = (
        db.query(ScanQueryResult.hallucination_flagged)
        .join(TrackedQuery, TrackedQuery.id == ScanQueryResult.tracked_query_id)
        .filter(
            TrackedQuery.client_id == client_id,
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.response_text.isnot(None),
            ScanQueryResult.observed_at >= lo,
            ScanQueryResult.observed_at <= hi,
        )
        .all()
    )
    if not rows:
        return None
    flagged = sum(1 for row in rows if row[0])
    return (len(rows) - flagged) / len(rows)


def _share_of_source(db: Session, client_id: uuid.UUID, start: date, end: date) -> float | None:
    """The client's own share of the sources AI answers drew on."""
    lo, hi = _window(start, end)
    row = (
        db.query(ShareOfSourceSnapshot.client_share_pct)
        .filter(
            ShareOfSourceSnapshot.client_id == client_id,
            ShareOfSourceSnapshot.computed_at >= lo,
            ShareOfSourceSnapshot.computed_at <= hi,
        )
        .order_by(ShareOfSourceSnapshot.computed_at.desc())
        .limit(1)
        .scalar()
    )
    return float(row) if row is not None else None


def _verified_action_rate(
    db: Session, client_id: uuid.UUID, start: date, end: date
) -> float | None:
    """Share of concluded delivery actions that reached verified.

    Denominator is concluded work only (`verified` plus `no_change`). Counting
    in-flight actions would make a client who is simply mid-cycle look like a
    client whose work failed.
    """
    lo, hi = _window(start, end)
    rows = (
        db.query(OutcomeAction.status)
        .filter(
            OutcomeAction.client_id == client_id,
            OutcomeAction.status.in_(("verified", "no_change")),
            OutcomeAction.verified_at >= lo,
            OutcomeAction.verified_at <= hi,
        )
        .all()
    )
    if not rows:
        return None
    verified = sum(1 for row in rows if row[0] == "verified")
    return verified / len(rows)


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    unit: str
    clip: tuple[float, float]
    calculation_version: str
    min_coverage: int
    extractor: Callable[[Session, uuid.UUID, date, date], float | None]
    # None means every pack. A metric only meaningful for some packs names them.
    allowed_packs: tuple[str, ...] | None = None


BENCHMARK_METRICS: dict[str, MetricDefinition] = {
    "ai_presence_score": MetricDefinition(
        key="ai_presence_score",
        unit="score_0_100",
        clip=(0.0, 100.0),
        calculation_version=SNAPSHOT_CALCULATION_VERSION,
        min_coverage=10,
        extractor=_ai_presence_score,
    ),
    "answer_stability_score": MetricDefinition(
        key="answer_stability_score",
        unit="score_0_100",
        clip=(0.0, 100.0),
        calculation_version=SNAPSHOT_CALCULATION_VERSION,
        min_coverage=30,
        extractor=_answer_stability_score,
    ),
    "accuracy_rate": MetricDefinition(
        key="accuracy_rate",
        unit="ratio_0_1",
        clip=(0.0, 1.0),
        calculation_version=SNAPSHOT_CALCULATION_VERSION,
        min_coverage=10,
        extractor=_accuracy_rate,
    ),
    # Named for the product's existing Share-of-Source vocabulary rather than
    # the plan's "citation_share": one concept, one name, and CLAUDE.md section 2
    # keeps citation language away from anything a client can read.
    "share_of_source": MetricDefinition(
        key="share_of_source",
        unit="percent_0_100",
        clip=(0.0, 100.0),
        calculation_version=SNAPSHOT_CALCULATION_VERSION,
        min_coverage=10,
        extractor=_share_of_source,
    ),
    "verified_action_rate": MetricDefinition(
        key="verified_action_rate",
        unit="ratio_0_1",
        clip=(0.0, 1.0),
        calculation_version=SNAPSHOT_CALCULATION_VERSION,
        min_coverage=10,
        extractor=_verified_action_rate,
    ),
}


# --- pure aggregation ---------------------------------------------------------


def clip_value(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    return float(min(max(value, low), high))


def percentile(sorted_values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile over an ascending series.

    Written out rather than taken from `statistics.quantiles`, whose method
    differs between definitions; a published figure must be reproducible from
    the documented formula alone.
    """
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = q * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def collect_metric_values(
    db: Session,
    metric: MetricDefinition,
    members: list[CohortEligibility],
    period_start: date,
    period_end: date,
) -> dict[uuid.UUID, float]:
    """One clipped value per contributing client. Non-contributors are absent."""
    values: dict[uuid.UUID, float] = {}
    for member in members:
        if not member.eligible:
            continue
        if member.measurement_coverage < metric.min_coverage:
            continue
        if metric.allowed_packs and member.spec and member.spec.industry_pack not in metric.allowed_packs:
            continue
        raw = metric.extractor(db, member.client_id, period_start, period_end)
        if raw is None:
            continue
        values[member.client_id] = clip_value(raw, metric.clip)
    return values


# --- persistence --------------------------------------------------------------


def get_or_create_cohort(
    db: Session, spec: CohortSpec, min_member_count: int = MIN_COHORT_MEMBER_FLOOR
) -> BenchmarkCohort:
    existing = (
        db.query(BenchmarkCohort)
        .filter(
            BenchmarkCohort.cohort_key == spec.cohort_key,
            BenchmarkCohort.definition_version == spec.definition_version,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    cohort = BenchmarkCohort(
        cohort_key=spec.cohort_key,
        definition_version=spec.definition_version,
        industry_pack=spec.industry_pack,
        subcategory=spec.subcategory,
        country_code=spec.country_code,
        market_area=spec.market_area,
        scale_band=spec.scale_band,
        coverage_band=spec.coverage_band,
        period_type=spec.period_type,
        min_member_count=max(min_member_count, MIN_COHORT_MEMBER_FLOOR),
    )
    db.add(cohort)
    db.commit()
    return cohort


def record_membership(
    db: Session,
    cohort: BenchmarkCohort,
    members: list[CohortEligibility],
    period_start: date,
    period_end: date,
) -> None:
    """Write the private audit trail of who counted and why the rest did not.

    Upserts on the (cohort, client, period) identity so a rerun corrects rather
    than duplicating.
    """
    for member in members:
        existing = (
            db.query(BenchmarkCohortMembership)
            .filter(
                BenchmarkCohortMembership.cohort_id == cohort.id,
                BenchmarkCohortMembership.client_id == member.client_id,
                BenchmarkCohortMembership.evaluation_period_start == period_start,
                BenchmarkCohortMembership.evaluation_period_end == period_end,
            )
            .one_or_none()
        )
        row = existing or BenchmarkCohortMembership(
            cohort_id=cohort.id,
            client_id=member.client_id,
            evaluation_period_start=period_start,
            evaluation_period_end=period_end,
        )
        row.is_included = member.eligible
        # The CHECK constraints require exactly one of these to be set.
        row.exclusion_reason = None if member.eligible else ",".join(member.reason_codes)[:64]
        row.measurement_coverage = member.measurement_coverage
        if existing is None:
            db.add(row)
    db.commit()


def _members_of(cohort: BenchmarkCohort, members: list[CohortEligibility]) -> list[CohortEligibility]:
    from app.services.benchmark_cohort_service import _matches, DEFAULT_COHORT_CONFIG

    target = CohortSpec(
        industry_pack=cohort.industry_pack,
        subcategory=cohort.subcategory,
        country_code=cohort.country_code,
        market_area=cohort.market_area,
        scale_band=cohort.scale_band,
        coverage_band=cohort.coverage_band,
        period_type=cohort.period_type,
        definition_version=cohort.definition_version,
    )
    return [
        member
        for member in members
        if member.spec is not None and _matches(member.spec, target, DEFAULT_COHORT_CONFIG)
    ]


def generate_snapshot(
    db: Session,
    cohort: BenchmarkCohort,
    members: list[CohortEligibility],
    metric_key: str,
    period_start: date,
    period_end: date,
    calculation_version: str | None = None,
    forced_suppression_reason: str | None = None,
) -> BenchmarkSnapshot:
    """Aggregate one metric for one cohort and persist an immutable snapshot.

    Raises KeyError for an unregistered metric: the registry is the whole
    vocabulary, and accepting a caller-chosen key would let someone slice until
    a cohort contained one client.
    """
    metric = BENCHMARK_METRICS[metric_key]
    version = calculation_version or metric.calculation_version

    existing = (
        db.query(BenchmarkSnapshot)
        .filter(
            BenchmarkSnapshot.cohort_id == cohort.id,
            BenchmarkSnapshot.period_start == period_start,
            BenchmarkSnapshot.period_end == period_end,
            BenchmarkSnapshot.metric_key == metric_key,
            BenchmarkSnapshot.calculation_version == version,
        )
        .one_or_none()
    )
    if existing is not None and existing.approved_at is not None:
        # Published numbers are never recalculated in place. A correction is a
        # new calculation version.
        return existing

    cohort_members = _members_of(cohort, members)
    values = collect_metric_values(db, metric, cohort_members, period_start, period_end)
    eligible_count = len(cohort_members)
    contributing_count = len(values)

    suppression_reason = forced_suppression_reason
    if suppression_reason is None:
        if eligible_count < cohort.min_member_count:
            suppression_reason = "cohort_below_minimum"
        elif contributing_count < MIN_METRIC_CONTRIBUTORS:
            suppression_reason = "insufficient_contributors"

    if suppression_reason is not None:
        logger.info(
            "benchmark snapshot suppressed",
            extra={
                "cohort_key": cohort.cohort_key,
                "metric_key": metric_key,
                "reason": suppression_reason,
                "eligible_member_count": eligible_count,
                "contributing_member_count": contributing_count,
            },
        )
        aggregates = dict(p25=None, p50=None, p75=None, mean=None)
    else:
        series = sorted(values.values())
        aggregates = dict(
            p25=percentile(series, 0.25),
            p50=percentile(series, 0.50),
            p75=percentile(series, 0.75),
            mean=sum(series) / len(series),
        )

    row = existing or BenchmarkSnapshot(
        cohort_id=cohort.id,
        period_start=period_start,
        period_end=period_end,
        metric_key=metric_key,
        calculation_version=version,
    )
    row.eligible_member_count = eligible_count
    row.contributing_member_count = contributing_count
    row.suppressed = suppression_reason is not None
    row.suppression_reason = suppression_reason
    row.generated_at = utcnow()
    for field, value in aggregates.items():
        setattr(row, field, value)
    if existing is None:
        db.add(row)
    db.commit()
    return row


def generate_ladder_snapshots(
    db: Session,
    spec: CohortSpec,
    members: list[CohortEligibility],
    metric_key: str,
    period_start: date,
    period_end: date,
) -> list[BenchmarkSnapshot]:
    """Generate every cohort on the widening ladder, then close the
    differencing gap between nested pairs.

    The ladder is nested by construction — each rung contains the one before
    it — so a broader rung whose contributor count exceeds the narrower one by
    fewer than `MIN_METRIC_CONTRIBUTORS` exposes that small difference group by
    subtraction. The broader rung is suppressed, never the narrower one: the
    narrow cohort is the client's own comparison and is the more useful of the
    two.
    """
    snapshots: list[BenchmarkSnapshot] = []
    for candidate in widening_ladder(spec):
        cohort = get_or_create_cohort(db, candidate)
        snapshots.append(
            generate_snapshot(db, cohort, members, metric_key, period_start, period_end)
        )

    # Compare each rung against the nearest *published* narrower rung, not
    # simply the previous one. Suppressing a middle rung does not remove the
    # subtraction: if the narrowest cohort publishes 10 and a rung two steps
    # out publishes 12, the two-client difference is exposed regardless of
    # what happened to the rung between them.
    last_published: BenchmarkSnapshot | None = None
    for snapshot in snapshots:
        if snapshot.suppressed:
            continue
        if last_published is not None:
            difference = (
                snapshot.contributing_member_count - last_published.contributing_member_count
            )
            if 0 < difference < MIN_METRIC_CONTRIBUTORS:
                generate_snapshot(
                    db,
                    snapshot.cohort,
                    members,
                    metric_key,
                    period_start,
                    period_end,
                    forced_suppression_reason="differencing_risk",
                )
                continue
        last_published = snapshot

    db.expire_all()
    return snapshots
