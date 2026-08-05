"""Per-query answer stability from repeated ScanQueryResult samples (Phase 5
Task 4 — see app/services/query_sampling_service.py for the sampler that
produces the repeated samples this module analyzes).

INDEPENDENT from GeoScore: this module never imports scoring_service and
nothing it computes feeds `overall_score`. It answers a different question
than the score does — not "is the brand doing well" but "do repeated
observations of the same tracked query agree with each other" — and is
meant to be shown alongside the score, never merged into it.

Design (see docs referenced in the Phase 5 plan):

  A "period" is one scan — every sample sharing a `scan_id` belongs to the
  same period, per `query_sampling_service`'s repeat-sampling within a scan.

  Four agreement dimensions are compared across samples:
    - brand_presence: was the brand seen by AI in the answer (CLAUDE.md
      section 2 language: "Seen by AI" / "Not seen by AI", never
      "cited"/"mentioned")
    - recommendation_status: was the brand recommended (i.e. ranked) in the
      answer
    - source_domain_set: which source domains were cited
    - position_band: coarse recommendation-position bucket (1-3, 4-6, 7+,
      not_found)

  A sample whose provider produced no answer at all (`response_text is
  None`) is UNOBSERVED for every dimension — never scored as a negative
  ("not seen") mention, since there is no answer to have seen or not seen
  the brand in.

State machine (`QueryStability.state`):
  insufficient  fewer than MIN_SAMPLE_COUNT (3) samples exist at all, OR
                every sample that exists is unobserved (nothing to compare)
  emerging      the query has real answers in only one period, but fewer
                than MIN_OBSERVED_FOR_REPEATED (2) of them — not enough to
                say the answer repeats, only that it appeared once
  repeated      >=2 observed samples in a single period agree with each
                other (min per-dimension agreement >= STABILITY_THRESHOLD)
  stable        >=2 periods each have a defined per-period consensus answer,
                and those consensus answers agree with each other across
                periods (>= STABILITY_THRESHOLD)
  volatile      enough observed samples to judge, but agreement falls below
                STABILITY_THRESHOLD — a material disagreement, not just a
                thin sample

`score` is the minimum agreement ratio across the four dimensions (the most
conservative reading — one badly-disagreeing dimension is enough to flag the
query), and is only None for the `insufficient` state; every other state has
at least one observed sample to compute a (possibly trivial, 1.0) ratio from.
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.models.tracked_query import TrackedQuery

# Below this many total sample rows (regardless of whether the provider
# actually answered), a query's stability can't be judged at all. Matches
# query_sampling_service.MIN_SAMPLE_COUNT deliberately — Task 3 already
# treats "fewer than 3 valid samples" as the bar for resampling priority, so
# this module treats it as the same bar for confidence in a verdict.
MIN_SAMPLE_COUNT = 3

# Within a single period, at least this many OBSERVED (non-unobserved)
# samples are needed before "the answer repeated" is a meaningful claim.
# One observed sample only shows the answer appeared once (state=emerging).
MIN_OBSERVED_FOR_REPEATED = 2

# Per-dimension agreement ratio below this is a material disagreement
# (state=volatile) rather than ordinary sampling noise.
STABILITY_THRESHOLD = 0.6

CALCULATION_VERSION = "stability_v1"

# Sentinel dimension value for a sample the provider never actually
# answered. Never treated as "brand not seen" / "not recommended" — those
# are real negative observations, this is the absence of one.
UNOBSERVED = "__unobserved__"


@dataclass(frozen=True)
class QueryStability:
    state: str  # one of "insufficient" | "emerging" | "repeated" | "stable" | "volatile"
    score: float | None
    sample_count: int
    period_count: int
    agreement: dict[str, float] = field(default_factory=dict)
    calculation_version: str = CALCULATION_VERSION
    # Populated by calculate_portfolio_stability (one query per portfolio
    # row); left None by calculate_query_stability, whose caller already
    # knows which tracked query it asked about.
    tracked_query_id: uuid.UUID | None = None


@dataclass(frozen=True)
class QuerySample:
    """One ScanQueryResult observation, reduced to what stability needs.

    Pure data — no DB session, no ORM lazy-loading — so `calculate_stability`
    is a pure function testable without a database (see query_sampling_service
    for the same pattern with SamplingPlan/FakeTrackedQuery).
    """

    scan_id: uuid.UUID
    sample_index: int
    observed_at: datetime
    observed: bool  # False when the provider returned no response_text at all
    brand_detected: bool
    recommendation_position: int | None
    source_domains: frozenset[str]


# ── pure dimension value extractors ──────────────────────────────────────
# Each takes an OBSERVED QuerySample (callers never invoke these on an
# unobserved sample) and returns a hashable value comparable across samples.


def _brand_presence_value(sample: QuerySample) -> str:
    return "seen" if sample.brand_detected else "not_seen"


def _recommendation_status_value(sample: QuerySample) -> str:
    return "recommended" if sample.recommendation_position is not None else "not_recommended"


def _position_band_value(sample: QuerySample) -> str:
    pos = sample.recommendation_position
    if pos is None:
        return "not_found"
    if pos <= 3:
        return "1-3"
    if pos <= 6:
        return "4-6"
    return "7+"


def _source_domain_set_value(sample: QuerySample) -> frozenset[str]:
    return sample.source_domains


# Iteration order here becomes the key order of QueryStability.agreement.
_DIMENSIONS: dict[str, Callable[[QuerySample], object]] = {
    "brand_presence": _brand_presence_value,
    "recommendation_status": _recommendation_status_value,
    "source_domain_set": _source_domain_set_value,
    "position_band": _position_band_value,
}


def _agreement_ratio(values: list) -> float:
    """Fraction of `values` matching the modal (most common) value. Callers
    only ever pass a non-empty list of already-observed values, so this
    always returns a defined ratio — never None."""
    counts = Counter(values)
    _, top_count = counts.most_common(1)[0]
    return top_count / len(values)


def _classify_single_period(samples: list[QuerySample]) -> tuple[str, float, dict[str, float]]:
    """Classify one period's worth of samples as emerging/repeated/volatile.

    Caller guarantees at least one observed sample among `samples` (see
    calculate_stability, which only reaches here after excluding the
    all-unobserved case as `insufficient`).
    """
    observed = [s for s in samples if s.observed]
    agreement = {name: _agreement_ratio([fn(s) for s in observed]) for name, fn in _DIMENSIONS.items()}
    score = min(agreement.values())

    if len(observed) < MIN_OBSERVED_FOR_REPEATED:
        state = "emerging"
    elif score < STABILITY_THRESHOLD:
        state = "volatile"
    else:
        state = "repeated"
    return state, score, agreement


def _group_by_period(samples: list[QuerySample]) -> dict[uuid.UUID, list[QuerySample]]:
    periods: dict[uuid.UUID, list[QuerySample]] = defaultdict(list)
    for sample in samples:
        periods[sample.scan_id].append(sample)
    return periods


def calculate_stability(samples: list[QuerySample]) -> QueryStability:
    """Pure calculation: repeated ScanQueryResult samples for ONE tracked
    query -> its current QueryStability. No DB access — see
    calculate_query_stability / calculate_portfolio_stability for the thin
    DB-backed wrappers that build `samples` and call this."""
    sample_count = len(samples)
    observed_total = sum(1 for s in samples if s.observed)
    periods = _group_by_period(samples)
    period_count = len(periods)

    if sample_count < MIN_SAMPLE_COUNT or observed_total == 0:
        return QueryStability(
            state="insufficient",
            score=None,
            sample_count=sample_count,
            period_count=period_count,
        )

    effective_periods = {
        scan_id: period_samples
        for scan_id, period_samples in periods.items()
        if any(s.observed for s in period_samples)
    }

    if len(effective_periods) == 1:
        (only_period_samples,) = effective_periods.values()
        state, score, agreement = _classify_single_period(only_period_samples)
        return QueryStability(
            state=state,
            score=score,
            sample_count=sample_count,
            period_count=period_count,
            agreement=agreement,
        )

    # >= 2 periods each produced at least one real answer: compare each
    # period's own consensus (its modal observed value per dimension)
    # against the other periods' consensus, rather than pooling every
    # sample together — a period with 3 samples should not out-vote another
    # period that only got 1 (design decision #3: period-level consensus).
    agreement: dict[str, float] = {}
    for name, fn in _DIMENSIONS.items():
        period_consensus = []
        for period_samples in effective_periods.values():
            observed_values = [fn(s) for s in period_samples if s.observed]
            period_consensus.append(Counter(observed_values).most_common(1)[0][0])
        agreement[name] = _agreement_ratio(period_consensus)

    score = min(agreement.values())
    state = "stable" if score >= STABILITY_THRESHOLD else "volatile"
    return QueryStability(
        state=state,
        score=score,
        sample_count=sample_count,
        period_count=period_count,
        agreement=agreement,
    )


# ── DB-backed wrappers ───────────────────────────────────────────────────


def _rows_to_samples(
    rows: list[ScanQueryResult], domains_by_result: dict[uuid.UUID, frozenset[str]]
) -> list[QuerySample]:
    return [
        QuerySample(
            scan_id=row.scan_id,
            sample_index=row.sample_index,
            observed_at=row.observed_at,
            observed=row.response_text is not None,
            brand_detected=bool(row.brand_detected),
            recommendation_position=row.recommendation_position,
            source_domains=domains_by_result.get(row.id, frozenset()),
        )
        for row in rows
    ]


def _load_domains_by_result(result_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, frozenset[str]]:
    if not result_ids:
        return {}
    rows = (
        db.query(ScanQuerySource.scan_query_result_id, ScanQuerySource.domain)
        .filter(ScanQuerySource.scan_query_result_id.in_(result_ids))
        .all()
    )
    grouped: dict[uuid.UUID, set[str]] = defaultdict(set)
    for result_id, domain in rows:
        grouped[result_id].add(domain)
    return {result_id: frozenset(domains) for result_id, domains in grouped.items()}


def calculate_query_stability(tracked_query_id: uuid.UUID, db: Session) -> QueryStability:
    """Read-only: loads every non-control ScanQueryResult sample linked to
    this tracked query and computes its current stability. Never writes."""
    rows = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.tracked_query_id == tracked_query_id,
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )
    domains_by_result = _load_domains_by_result([row.id for row in rows], db)
    return calculate_stability(_rows_to_samples(rows, domains_by_result))


def calculate_portfolio_stability(
    client_id: uuid.UUID,
    db: Session,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[QueryStability]:
    """Read-only: one QueryStability per active-or-inactive tracked query
    owned by this client (every governed query in the portfolio, so a
    caller can see which ones have no samples yet at all). Batches the
    ScanQueryResult / ScanQuerySource reads into two queries total instead
    of one pair per tracked query.

    `period_start`/`period_end` bound which observations are considered.
    Unbounded by default, which is what the live portfolio view wants. Phase 6
    benchmark snapshots pass a window because a snapshot is an immutable
    historical record: recomputing July's cohort from today's samples would
    make an approved number irreproducible."""
    tracked_query_ids = [
        row[0] for row in db.query(TrackedQuery.id).filter(TrackedQuery.client_id == client_id).all()
    ]
    if not tracked_query_ids:
        return []

    query = db.query(ScanQueryResult).filter(
        ScanQueryResult.tracked_query_id.in_(tracked_query_ids),
        ScanQueryResult.is_control.is_(False),
    )
    if period_start is not None:
        query = query.filter(ScanQueryResult.observed_at >= period_start)
    if period_end is not None:
        query = query.filter(ScanQueryResult.observed_at <= period_end)
    rows = query.all()
    domains_by_result = _load_domains_by_result([row.id for row in rows], db)

    samples_by_tracked_query: dict[uuid.UUID, list[ScanQueryResult]] = defaultdict(list)
    for row in rows:
        samples_by_tracked_query[row.tracked_query_id].append(row)

    results = []
    for tracked_query_id in tracked_query_ids:
        stability = calculate_stability(
            _rows_to_samples(samples_by_tracked_query.get(tracked_query_id, []), domains_by_result)
        )
        results.append(
            QueryStability(
                state=stability.state,
                score=stability.score,
                sample_count=stability.sample_count,
                period_count=stability.period_count,
                agreement=stability.agreement,
                calculation_version=stability.calculation_version,
                tracked_query_id=tracked_query_id,
            )
        )
    return results
