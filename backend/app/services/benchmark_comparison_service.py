# backend/app/services/benchmark_comparison_service.py
"""Turn approved snapshots into one client's comparison.

Only approved snapshots are ever read. An unapproved snapshot is a draft
aggregate that nobody has reviewed, and showing one to a client would make the
review gate decorative.

The narrowest approved cohort on the client's own ladder wins. That is the most
meaningful comparison available — a Kuala Lumpur dental practice would rather
be compared against KL dental practices than against every healthcare business
in Malaysia — and the ladder guarantees the fallback is still a population the
client genuinely belongs to.

Nothing here reads a caller-supplied filter. The cohort comes from the client's
own attributes; there is no parameter a caller could use to slice a cohort down
until it contained one organization.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.benchmark_cohort import BenchmarkCohort
from app.models.benchmark_snapshot import BenchmarkSnapshot
from app.models.client import Client
from app.schemas.benchmark_comparison import (
    DEFAULT_CAVEAT,
    METRIC_LABELS,
    SUPPRESSION_MESSAGES,
    BenchmarkComparison,
    member_count_band,
    percentile_band,
)
from app.services.benchmark_cohort_service import (
    evaluate_client_eligibility,
    widening_ladder,
)
from app.services.benchmark_snapshot_service import BENCHMARK_METRICS

# Human-readable cohort labels. Deliberately says "comparable SeenBy clients",
# never "your competitors": the cohort is a privacy-protected peer group, and
# implying it is the client's competitive set would be a claim we cannot
# substantiate from it.
PACK_LABELS = {
    "healthcare": "healthcare businesses",
    "fnb": "food and beverage businesses",
    "local_services": "local service businesses",
}
SCALE_LABELS = {
    "single_location": "single-location",
    "small_multi_location": "small multi-location",
    "large_multi_location": "large multi-location",
    "single_or_small_location": "single and small multi-location",
}


def cohort_label(cohort: BenchmarkCohort) -> str:
    pack = PACK_LABELS.get(cohort.industry_pack, "businesses")
    scale = SCALE_LABELS.get(cohort.scale_band)
    where = cohort.market_area.replace("-", " ").title() if cohort.market_area else None
    parts = ["Comparable SeenBy clients:", scale, pack] if scale else ["Comparable SeenBy clients:", pack]
    label = " ".join(part for part in parts if part)
    if where:
        return f"{label} in {where}"
    return f"{label} in {cohort.country_code}"


def _approved_snapshot(
    db: Session,
    cohort_key: str,
    definition_version: str,
    metric_key: str,
    period_start: date,
    period_end: date,
    calculation_version: str,
) -> tuple[BenchmarkCohort, BenchmarkSnapshot] | None:
    row = (
        db.query(BenchmarkCohort, BenchmarkSnapshot)
        .join(BenchmarkSnapshot, BenchmarkSnapshot.cohort_id == BenchmarkCohort.id)
        .filter(
            BenchmarkCohort.cohort_key == cohort_key,
            BenchmarkCohort.definition_version == definition_version,
            BenchmarkSnapshot.metric_key == metric_key,
            BenchmarkSnapshot.period_start == period_start,
            BenchmarkSnapshot.period_end == period_end,
            BenchmarkSnapshot.calculation_version == calculation_version,
            BenchmarkSnapshot.approved_at.isnot(None),
        )
        .one_or_none()
    )
    return row


def _suppressed(
    metric_key: str,
    period_start: date,
    period_end: date,
    reason: str,
    label: str = "Comparable SeenBy clients",
    client_value: float | None = None,
) -> BenchmarkComparison:
    return BenchmarkComparison(
        metric_key=metric_key,
        metric_label=METRIC_LABELS.get(metric_key, metric_key),
        client_value=client_value,
        cohort_label=label,
        period_start=period_start,
        period_end=period_end,
        suppressed=True,
        suppression_reason=reason,
        suppression_message=SUPPRESSION_MESSAGES.get(reason),
        caveat=DEFAULT_CAVEAT,
    )


def get_client_comparisons(
    db: Session,
    client: Client,
    period_start: date,
    period_end: date,
) -> list[BenchmarkComparison]:
    """One comparison per registered metric, suppressed where it must be."""
    eligibility = evaluate_client_eligibility(db, client, period_start, period_end)
    if not eligibility.eligible or eligibility.spec is None:
        return [
            _suppressed(metric_key, period_start, period_end, "not_eligible")
            for metric_key in BENCHMARK_METRICS
        ]

    ladder = widening_ladder(eligibility.spec)
    comparisons: list[BenchmarkComparison] = []

    for metric_key, metric in BENCHMARK_METRICS.items():
        client_value = metric.extractor(db, client.id, period_start, period_end)

        found = None
        for candidate in ladder:
            found = _approved_snapshot(
                db,
                candidate.cohort_key,
                candidate.definition_version,
                metric_key,
                period_start,
                period_end,
                metric.calculation_version,
            )
            if found is not None and not found[1].suppressed:
                break
            found = None

        if found is None:
            comparisons.append(
                _suppressed(
                    metric_key, period_start, period_end, "no_cohort", client_value=client_value
                )
            )
            continue

        cohort, snapshot = found
        if client_value is None:
            comparisons.append(
                _suppressed(
                    metric_key,
                    period_start,
                    period_end,
                    "no_client_value",
                    label=cohort_label(cohort),
                )
            )
            continue

        comparisons.append(
            BenchmarkComparison(
                metric_key=metric_key,
                metric_label=METRIC_LABELS.get(metric_key, metric_key),
                client_value=round(float(client_value), 2),
                percentile_band=percentile_band(
                    float(client_value), float(snapshot.p25), float(snapshot.p75)
                ),
                cohort_label=cohort_label(cohort),
                cohort_key=cohort.cohort_key,
                eligible_member_count=snapshot.eligible_member_count,
                contributing_member_count=snapshot.contributing_member_count,
                p25=float(snapshot.p25),
                p50=float(snapshot.p50),
                p75=float(snapshot.p75),
                period_start=snapshot.period_start,
                period_end=snapshot.period_end,
                member_count_band=member_count_band(snapshot.contributing_member_count),
                calculation_version=snapshot.calculation_version,
                suppressed=False,
                caveat=DEFAULT_CAVEAT,
            )
        )

    return comparisons
