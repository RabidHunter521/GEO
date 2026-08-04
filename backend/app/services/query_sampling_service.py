# backend/app/services/query_sampling_service.py
"""Budget-aware repeat sampling for the governed tracked-query portfolio
(Phase 5 Task 3 — see docs/superpowers/plans/2026-07-29-seenby-measurement-
business-proof.md).

A `TrackedQuery` (app/models/tracked_query.py) is a durable identity a client
wants observed repeatedly across scans, so answer stability can eventually be
measured (Task 4's `query_stability_service`, not built yet). This module
decides, for one scan, WHICH tracked queries get resampled and HOW MANY times
— deterministically, so the same inputs always produce the same plan (no
`random`, no wall-clock reads inside the scheduling function itself).

Selection priority (highest first), matching the Task 3 brief:

  1. high-risk queries               (risk_level in elevated/critical)
  2. high-value queries with a recently changed answer
  3. queries below the minimum valid sample count
  4. a rotating slice of the remaining baseline pool

A query already selected by a higher tier is never demoted by a lower one —
it keeps ALL the reason codes that apply, but only the higher tier's
repetition count. Inactive queries are filtered out before any tier runs, so
step 5 of the brief ("never sample an inactive query") holds by construction,
not by omission.

`recent_change_ids` has no real producer yet — Task 4 (answer stability) is
the natural place to compute "the last two samples disagree," and reusing
that logic here ahead of time would duplicate work Task 4 has to redo
correctly anyway. `scan_service.run_scan` currently passes an empty set for
it; the parameter exists now so Task 4 only has to supply a value, not touch
this module's contract.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.scan_query_result import ScanQueryResult
from app.models.tracked_query import TrackedQuery

# Repeated-sample counts. "High priority" covers every tier except the
# rotating baseline; the brief calls for 3 vs 1 specifically, not a gradient.
HIGH_PRIORITY_REPETITIONS = 3
BASELINE_REPETITIONS = 1

# A tracked query needs at least this many valid samples before it stops
# being flagged as "lacking the minimum sample count." Matches Task 4's
# planned "insufficient" stability state threshold (fewer than 3 samples).
MIN_SAMPLE_COUNT = 3

# How many additional (non-tiered) queries the rotating baseline pulls in per
# scan. Deliberately small — the baseline exists to eventually cover the
# whole portfolio over many scans, not to resample everything at once.
DEFAULT_BASELINE_POOL_SIZE = 3

# Rough, deliberately conservative average cost per single query sample
# across scan platforms, used ONLY to cap this add-on's plan against
# remaining budget headroom before real per-call costs are known (see
# app.services.cost_tracker._TOKEN_COST for the real, per-model rates that
# get logged once a call actually happens). This is a planning estimate, not
# a billed amount, and is never written to llm_call_logs.
ESTIMATED_COST_PER_SAMPLE_USD = Decimal("0.01")

# Identifies which prompt template produced a tracked-query sample's
# query_text. Tracked-query text is verbatim admin-authored text (no
# template substitution, unlike QUERY_TEMPLATES), so this exists to let a
# future re-phrasing feature bump it without touching this module's callers.
TRACKED_QUERY_PROMPT_VERSION = "v1"

REASON_HIGH_RISK = "high_risk"
REASON_RECENT_CHANGE = "recent_change"
REASON_INSUFFICIENT_SAMPLES = "insufficient_samples"
REASON_BASELINE_ROTATION = "baseline_rotation"

# Drop order when the plan must be trimmed to fit a budget: least-protected
# reason first. A plan is only eligible to be dropped in a given round if
# THIS is its most-protected reason — a query that is both high-risk and
# under-sampled is never dropped for being under-sampled.
_REASON_PROTECTION_RANK = {
    REASON_HIGH_RISK: 0,
    REASON_RECENT_CHANGE: 1,
    REASON_INSUFFICIENT_SAMPLES: 2,
    REASON_BASELINE_ROTATION: 3,
}
_HIGH_RISK_LEVELS = frozenset({"elevated", "critical"})


@dataclass(frozen=True)
class SamplingPlan:
    tracked_query_id: uuid.UUID
    repetitions: int
    reason_codes: tuple[str, ...]
    estimated_cost_usd: Decimal


def build_sampling_plans(
    tracked_queries: list[TrackedQuery],
    *,
    sample_counts: dict[uuid.UUID, int] | None = None,
    recent_change_ids: set[uuid.UUID] | None = None,
    rotation_seed: int = 0,
    baseline_pool_size: int = DEFAULT_BASELINE_POOL_SIZE,
    remaining_budget_usd: Decimal | None = None,
) -> list[SamplingPlan]:
    """Deterministically select which tracked queries get repeated samples
    this scan.

    `sample_counts` is the existing valid-sample count per tracked query id;
    omitted ids are treated as 0. `recent_change_ids` is the set of tracked
    query ids whose answer recently changed. `rotation_seed` picks the
    starting point of the baseline slice — the same seed always yields the
    same slice, but callers (see scan_service) vary it scan-over-scan so the
    baseline eventually rotates through the whole untiered pool instead of
    always sampling the same head of the list. `remaining_budget_usd=None`
    means uncapped; a cap trims lowest-protection plans first via
    `_cap_to_budget`, mirroring budget_service's "never bypass the cap"
    contract rather than silently overspending.

    Returned order matches `tracked_queries` sorted by
    (priority_score desc, created_at asc, id asc) — the same ordering
    tracked_query_service.list_tracked_queries uses — so two calls with
    identical inputs always produce identical output.
    """
    sample_counts = sample_counts or {}
    recent_change_ids = recent_change_ids or set()

    active = sorted(
        (tq for tq in tracked_queries if tq.is_active),
        key=lambda tq: (-tq.priority_score, tq.created_at, str(tq.id)),
    )

    # tracked_query_id -> (repetitions, [reason codes in tier order]).
    tiered: dict[uuid.UUID, tuple[int, list[str]]] = {}

    def _tag(tq_id: uuid.UUID, reason: str) -> None:
        _, reasons = tiered.get(tq_id, (0, []))
        if reason not in reasons:
            reasons = [*reasons, reason]
        tiered[tq_id] = (HIGH_PRIORITY_REPETITIONS, reasons)

    for tq in active:
        if tq.risk_level in _HIGH_RISK_LEVELS:
            _tag(tq.id, REASON_HIGH_RISK)
    for tq in active:
        if tq.id in recent_change_ids:
            _tag(tq.id, REASON_RECENT_CHANGE)
    for tq in active:
        if sample_counts.get(tq.id, 0) < MIN_SAMPLE_COUNT:
            _tag(tq.id, REASON_INSUFFICIENT_SAMPLES)

    # Rotating baseline: queries not already tiered above, taken as a
    # deterministic slice of the remaining pool starting at
    # `rotation_seed % len(remaining)`, wrapping around.
    remaining = [tq for tq in active if tq.id not in tiered]
    if remaining and baseline_pool_size > 0:
        start = rotation_seed % len(remaining)
        rotated = remaining[start:] + remaining[:start]
        for tq in rotated[:baseline_pool_size]:
            reps, reasons = tiered.get(tq.id, (0, []))
            tiered[tq.id] = (BASELINE_REPETITIONS, [*reasons, REASON_BASELINE_ROTATION])

    plans = [
        SamplingPlan(
            tracked_query_id=tq.id,
            repetitions=tiered[tq.id][0],
            reason_codes=tuple(tiered[tq.id][1]),
            estimated_cost_usd=ESTIMATED_COST_PER_SAMPLE_USD * tiered[tq.id][0],
        )
        for tq in active
        if tq.id in tiered
    ]

    if remaining_budget_usd is not None:
        plans = _cap_to_budget(plans, remaining_budget_usd)
    return plans


def _plan_protection_rank(plan: SamplingPlan) -> int:
    """The most-protected reason a plan carries — the lowest rank among its
    reason codes wins, so a query tagged both high_risk and baseline reads
    as high_risk-protected."""
    return min(_REASON_PROTECTION_RANK[r] for r in plan.reason_codes)


def _cap_to_budget(plans: list[SamplingPlan], remaining_budget_usd: Decimal) -> list[SamplingPlan]:
    """Drop plans, least-protected first, until total estimated cost fits.
    A negative headroom (budget already exceeded) is treated as zero — never
    negative, so the loop still terminates by dropping everything droppable
    rather than looping forever trying to reach a negative target."""
    if remaining_budget_usd < 0:
        remaining_budget_usd = Decimal("0")

    kept = list(plans)
    total = sum((p.estimated_cost_usd for p in kept), Decimal("0"))
    if total <= remaining_budget_usd:
        return kept

    for drop_reason in sorted(_REASON_PROTECTION_RANK, key=_REASON_PROTECTION_RANK.get, reverse=True):
        if total <= remaining_budget_usd:
            break
        drop_rank = _REASON_PROTECTION_RANK[drop_reason]
        for plan in list(kept):
            if total <= remaining_budget_usd:
                break
            # Only drop a plan whose MOST-protected reason is this tier — a
            # high_risk+baseline plan's most-protected reason is high_risk
            # (rank 0), so it is skipped in every round except high_risk's.
            if _plan_protection_rank(plan) != drop_rank:
                continue
            kept.remove(plan)
            total -= plan.estimated_cost_usd
    return kept


def expand_plans_to_query_specs(
    plans: list[SamplingPlan],
    tracked_queries_by_id: dict[uuid.UUID, TrackedQuery],
) -> list[dict]:
    """Turn plans into flat per-sample query specs for the scan engine —
    one dict per (tracked_query, sample_index), sample_index numbered
    1..repetitions per tracked query. Since each tracked_query_id appears in
    at most one plan and sample_index never repeats within that plan, the
    (tracked_query_id, sample_index) pairs returned are unique by
    construction — and, per platform dispatch in scan_service, so is the
    resulting (tracked_query_id, model_name, sample_index) triple."""
    specs: list[dict] = []
    for plan in plans:
        tq = tracked_queries_by_id[plan.tracked_query_id]
        specs.extend(
            {
                "category": tq.intent,
                "query_text": tq.text,
                "tracked_query_id": tq.id,
                "sample_index": sample_index,
                "prompt_version": TRACKED_QUERY_PROMPT_VERSION,
            }
            for sample_index in range(1, plan.repetitions + 1)
        )
    return specs


def existing_sample_counts(tracked_query_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, int]:
    """Count of ScanQueryResult rows already linked to each tracked query,
    across all past scans. Used to feed `sample_counts` above. Returns an
    empty dict without querying when given no ids, so a client with no
    tracked queries never issues this query."""
    if not tracked_query_ids:
        return {}
    rows = (
        db.query(ScanQueryResult.tracked_query_id, func.count(ScanQueryResult.id))
        .filter(ScanQueryResult.tracked_query_id.in_(tracked_query_ids))
        .group_by(ScanQueryResult.tracked_query_id)
        .all()
    )
    return {tracked_query_id: count for tracked_query_id, count in rows}
