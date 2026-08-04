# backend/tests/test_query_sampling_service.py
import uuid
from datetime import datetime
from decimal import Decimal

from app.services import query_sampling_service as sampling
from app.services.query_sampling_service import SamplingPlan


class FakeTrackedQuery:
    """Lightweight stand-in for the TrackedQuery ORM model — the scheduler
    only reads these attributes, never writes or queries through it."""

    def __init__(
        self,
        *,
        id=None,
        text="best acme dental clinic",
        intent="recommendation",
        risk_level="standard",
        priority_score=50.0,
        is_active=True,
        created_at=None,
    ):
        self.id = id or uuid.uuid4()
        self.text = text
        self.intent = intent
        self.risk_level = risk_level
        self.priority_score = priority_score
        self.is_active = is_active
        self.created_at = created_at or datetime(2026, 1, 1)


def _tq(**kwargs) -> FakeTrackedQuery:
    return FakeTrackedQuery(**kwargs)


# ── selection priorities (brief Step 1, items 1-5) ───────────────────────────

def test_selects_high_risk_queries():
    critical = _tq(risk_level="critical")
    standard = _tq(risk_level="standard")

    plans = sampling.build_sampling_plans(
        [critical, standard],
        # sufficiently sampled so `standard` isn't ALSO tagged
        # insufficient_samples, which would confound this assertion.
        sample_counts={standard.id: sampling.MIN_SAMPLE_COUNT},
        baseline_pool_size=0,
    )

    by_id = {p.tracked_query_id: p for p in plans}
    assert critical.id in by_id
    assert sampling.REASON_HIGH_RISK in by_id[critical.id].reason_codes
    assert by_id[critical.id].repetitions == sampling.HIGH_PRIORITY_REPETITIONS
    assert standard.id not in by_id


def test_selects_high_value_queries_with_recent_changes():
    changed = _tq()
    unchanged = _tq()

    plans = sampling.build_sampling_plans(
        [changed, unchanged],
        recent_change_ids={changed.id},
        # sufficiently sampled so `unchanged` isn't ALSO tagged
        # insufficient_samples, which would confound this assertion.
        sample_counts={unchanged.id: sampling.MIN_SAMPLE_COUNT},
        baseline_pool_size=0,
    )

    by_id = {p.tracked_query_id: p for p in plans}
    assert changed.id in by_id
    assert sampling.REASON_RECENT_CHANGE in by_id[changed.id].reason_codes
    assert by_id[changed.id].repetitions == sampling.HIGH_PRIORITY_REPETITIONS
    assert unchanged.id not in by_id


def test_selects_queries_lacking_minimum_sample_count():
    under_sampled = _tq()
    sufficiently_sampled = _tq()

    plans = sampling.build_sampling_plans(
        [under_sampled, sufficiently_sampled],
        sample_counts={
            under_sampled.id: sampling.MIN_SAMPLE_COUNT - 1,
            sufficiently_sampled.id: sampling.MIN_SAMPLE_COUNT,
        },
        baseline_pool_size=0,
    )

    by_id = {p.tracked_query_id: p for p in plans}
    assert under_sampled.id in by_id
    assert sampling.REASON_INSUFFICIENT_SAMPLES in by_id[under_sampled.id].reason_codes
    assert sufficiently_sampled.id not in by_id


def test_missing_sample_count_defaults_to_zero_and_is_flagged():
    """A tracked query absent from sample_counts (never sampled) must be
    treated as 0 valid samples, not skipped."""
    never_sampled = _tq()

    plans = sampling.build_sampling_plans([never_sampled], sample_counts={}, baseline_pool_size=0)

    assert len(plans) == 1
    assert sampling.REASON_INSUFFICIENT_SAMPLES in plans[0].reason_codes


def test_rotating_baseline_sample_selects_untiered_queries():
    baseline_candidates = [_tq() for _ in range(5)]
    high_risk = _tq(risk_level="critical")

    plans = sampling.build_sampling_plans(
        [high_risk, *baseline_candidates],
        sample_counts={tq.id: sampling.MIN_SAMPLE_COUNT for tq in [high_risk, *baseline_candidates]},
        baseline_pool_size=2,
        rotation_seed=0,
    )

    baseline_plans = [p for p in plans if p.reason_codes == (sampling.REASON_BASELINE_ROTATION,)]
    assert len(baseline_plans) == 2
    assert all(p.repetitions == sampling.BASELINE_REPETITIONS for p in baseline_plans)


def test_rotating_baseline_moves_with_the_seed():
    candidates = [_tq(priority_score=100 - i) for i in range(6)]
    sufficient_counts = {tq.id: sampling.MIN_SAMPLE_COUNT for tq in candidates}

    plans_seed_0 = sampling.build_sampling_plans(
        candidates,
        sample_counts=sufficient_counts,
        baseline_pool_size=2,
        rotation_seed=0,
    )
    plans_seed_3 = sampling.build_sampling_plans(
        candidates,
        sample_counts=sufficient_counts,
        baseline_pool_size=2,
        rotation_seed=3,
    )

    ids_seed_0 = {p.tracked_query_id for p in plans_seed_0}
    ids_seed_3 = {p.tracked_query_id for p in plans_seed_3}
    assert ids_seed_0 != ids_seed_3


def test_never_selects_an_inactive_query():
    inactive_high_risk = _tq(risk_level="critical", is_active=False)
    active = _tq()

    plans = sampling.build_sampling_plans(
        [inactive_high_risk, active],
        recent_change_ids={inactive_high_risk.id},
        sample_counts={inactive_high_risk.id: 0},
        baseline_pool_size=5,
    )

    selected_ids = {p.tracked_query_id for p in plans}
    assert inactive_high_risk.id not in selected_ids


# ── determinism ───────────────────────────────────────────────────────────────

def test_deterministic_for_identical_inputs():
    queries = [_tq(), _tq(risk_level="critical"), _tq(priority_score=10)]
    kwargs = dict(
        sample_counts={q.id: 1 for q in queries},
        recent_change_ids={queries[0].id},
        rotation_seed=7,
        baseline_pool_size=1,
    )

    first = sampling.build_sampling_plans(list(queries), **kwargs)
    second = sampling.build_sampling_plans(list(queries), **kwargs)

    assert first == second


# ── no duplicate (tracked_query_id, model_name, sample_index) ───────────────

def test_expand_plans_produces_no_duplicate_sample_indices():
    tq_a, tq_b = _tq(), _tq()
    plans = [
        SamplingPlan(tq_a.id, repetitions=3, reason_codes=(sampling.REASON_HIGH_RISK,), estimated_cost_usd=Decimal("0.03")),
        SamplingPlan(tq_b.id, repetitions=1, reason_codes=(sampling.REASON_BASELINE_ROTATION,), estimated_cost_usd=Decimal("0.01")),
    ]

    specs = sampling.expand_plans_to_query_specs(plans, {tq_a.id: tq_a, tq_b.id: tq_b})

    keys = [(s["tracked_query_id"], s["sample_index"]) for s in specs]
    assert len(keys) == len(set(keys))
    assert len(specs) == 4  # 3 + 1
    # Within one platform dispatch, model_name is constant per call, so the
    # (tracked_query_id, model_name, sample_index) triple inherits this same
    # no-duplicate guarantee for any fixed model_name.
    triples = [(k[0], "gpt-5-mini", k[1]) for k in keys]
    assert len(triples) == len(set(triples))


def test_expand_plans_numbers_samples_from_one():
    tq = _tq()
    plans = [SamplingPlan(tq.id, repetitions=3, reason_codes=(sampling.REASON_HIGH_RISK,), estimated_cost_usd=Decimal("0.03"))]

    specs = sampling.expand_plans_to_query_specs(plans, {tq.id: tq})

    assert [s["sample_index"] for s in specs] == [1, 2, 3]
    assert all(s["query_text"] == tq.text for s in specs)
    assert all(s["category"] == tq.intent for s in specs)
    assert all(s["tracked_query_id"] == tq.id for s in specs)


# ── repetitions: 3 high-priority / 1 baseline ────────────────────────────────

def test_high_priority_default_is_three_repetitions():
    tq = _tq(risk_level="critical")
    plans = sampling.build_sampling_plans([tq], baseline_pool_size=0)
    assert plans[0].repetitions == 3


def test_baseline_default_is_one_repetition():
    tq = _tq()
    plans = sampling.build_sampling_plans(
        [tq], sample_counts={tq.id: sampling.MIN_SAMPLE_COUNT}, baseline_pool_size=1,
    )
    assert plans[0].repetitions == 1
    assert plans[0].reason_codes == (sampling.REASON_BASELINE_ROTATION,)


# ── budget capping ────────────────────────────────────────────────────────────

def test_uncapped_when_remaining_budget_is_none():
    queries = [_tq(risk_level="critical") for _ in range(5)]
    plans = sampling.build_sampling_plans(queries, baseline_pool_size=0, remaining_budget_usd=None)
    assert len(plans) == 5


def test_budget_cap_drops_baseline_before_high_risk():
    high_risk = _tq(risk_level="critical")
    baseline_candidates = [_tq() for _ in range(3)]
    all_queries = [high_risk, *baseline_candidates]

    # Budget for exactly the high-risk query's 3 reps and nothing else.
    tight_budget = sampling.ESTIMATED_COST_PER_SAMPLE_USD * 3

    plans = sampling.build_sampling_plans(
        all_queries,
        sample_counts={tq.id: sampling.MIN_SAMPLE_COUNT for tq in all_queries},
        baseline_pool_size=3,
        remaining_budget_usd=tight_budget,
    )

    assert len(plans) == 1
    assert plans[0].tracked_query_id == high_risk.id


def test_budget_cap_never_bypassed_total_cost_fits():
    queries = [_tq(risk_level="critical") for _ in range(4)]
    budget = sampling.ESTIMATED_COST_PER_SAMPLE_USD * 5  # room for < 2 full plans

    plans = sampling.build_sampling_plans(queries, baseline_pool_size=0, remaining_budget_usd=budget)

    total = sum((p.estimated_cost_usd for p in plans), Decimal("0"))
    assert total <= budget


def test_negative_headroom_drops_everything_droppable():
    queries = [_tq() for _ in range(3)]
    plans = sampling.build_sampling_plans(
        queries,
        sample_counts={},
        baseline_pool_size=0,
        remaining_budget_usd=Decimal("-5"),
    )
    assert plans == []


# ── existing_sample_counts (DB-backed) ───────────────────────────────────────

def test_existing_sample_counts_empty_ids_skips_query(db):
    assert sampling.existing_sample_counts([], db) == {}


def test_existing_sample_counts_counts_rows_per_tracked_query(db):
    from app.models.client import Client
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.tracked_query import TrackedQuery

    client = Client(name="Acme", website="https://acme.com", industry="dental")
    db.add(client)
    db.commit()

    scan = Scan(client_id=client.id, platform="multi", status="completed")
    db.add(scan)
    db.commit()

    tq_a = TrackedQuery(
        client_id=client.id, text="best acme dental", normalized_text="best acme dental",
        source="manual", intent="recommendation",
    )
    tq_b = TrackedQuery(
        client_id=client.id, text="acme vs rival", normalized_text="acme vs rival",
        source="manual", intent="comparison",
    )
    db.add_all([tq_a, tq_b])
    db.commit()

    db.add_all([
        ScanQueryResult(scan_id=scan.id, platform="gemini", category="recommendation",
                         query_text=tq_a.text, tracked_query_id=tq_a.id, sample_index=1),
        ScanQueryResult(scan_id=scan.id, platform="gemini", category="recommendation",
                         query_text=tq_a.text, tracked_query_id=tq_a.id, sample_index=2),
        ScanQueryResult(scan_id=scan.id, platform="gemini", category="comparison",
                         query_text=tq_b.text, tracked_query_id=tq_b.id, sample_index=1),
        # Untracked row (legacy) must not be counted against either query.
        ScanQueryResult(scan_id=scan.id, platform="gemini", category="brand",
                         query_text="untracked"),
    ])
    db.commit()

    counts = sampling.existing_sample_counts([tq_a.id, tq_b.id], db)

    assert counts == {tq_a.id: 2, tq_b.id: 1}
