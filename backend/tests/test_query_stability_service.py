# backend/tests/test_query_stability_service.py
import uuid
from datetime import datetime

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.models.tracked_query import TrackedQuery
from app.services import query_stability_service as stability
from app.services.query_stability_service import QuerySample


# ── pure-function tests: calculate_stability(list[QuerySample]) ─────────────
# No DB involved — samples are built by hand, matching the FakeTrackedQuery
# pattern in test_query_sampling_service.py.


def _sample(
    *,
    scan_id=None,
    sample_index=1,
    observed=True,
    brand_detected=True,
    recommendation_position=None,
    source_domains=(),
    observed_at=None,
) -> QuerySample:
    return QuerySample(
        scan_id=scan_id or uuid.uuid4(),
        sample_index=sample_index,
        observed_at=observed_at or datetime(2026, 1, 1),
        observed=observed,
        brand_detected=brand_detected,
        recommendation_position=recommendation_position,
        source_domains=frozenset(source_domains),
    )


# ── insufficient ──────────────────────────────────────────────────────────


def test_zero_samples_is_insufficient():
    result = stability.calculate_stability([])
    assert result.state == "insufficient"
    assert result.score is None
    assert result.sample_count == 0
    assert result.period_count == 0
    assert result.agreement == {}


def test_fewer_than_minimum_samples_is_insufficient():
    scan_id = uuid.uuid4()
    samples = [_sample(scan_id=scan_id, sample_index=i) for i in range(1, stability.MIN_SAMPLE_COUNT)]

    result = stability.calculate_stability(samples)

    assert result.state == "insufficient"
    assert result.score is None
    assert result.sample_count == stability.MIN_SAMPLE_COUNT - 1


def test_all_unobserved_samples_is_insufficient_even_with_enough_rows():
    """Provider never actually answered any of the samples — there is
    nothing to compare, regardless of row count."""
    scan_id = uuid.uuid4()
    samples = [_sample(scan_id=scan_id, sample_index=i, observed=False) for i in range(1, 5)]

    result = stability.calculate_stability(samples)

    assert result.state == "insufficient"
    assert result.score is None


def test_unobserved_sample_is_not_scored_as_brand_not_seen():
    """Missing provider output is unobserved, not a negative mention — an
    unobserved sample must never drag brand_presence agreement down as if
    it disagreed by saying 'not seen'."""
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, observed=True, brand_detected=True),
        _sample(scan_id=scan_id, sample_index=2, observed=True, brand_detected=True),
        _sample(scan_id=scan_id, sample_index=3, observed=False),
    ]

    result = stability.calculate_stability(samples)

    # Only the 2 observed samples count, and they agree perfectly.
    assert result.agreement["brand_presence"] == 1.0
    assert result.state == "repeated"


# ── emerging ──────────────────────────────────────────────────────────────


def test_single_observed_sample_in_one_period_is_emerging():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, observed=True),
        _sample(scan_id=scan_id, sample_index=2, observed=False),
        _sample(scan_id=scan_id, sample_index=3, observed=False),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "emerging"
    assert result.sample_count == 3
    assert result.period_count == 1
    # A single observed sample trivially agrees with itself on every
    # dimension — score is a float, not None, even in the emerging state.
    assert result.score == 1.0


def test_emerging_when_only_one_period_has_any_observed_answer():
    """Total samples span 2 scans, but only one scan actually produced a
    real answer — not enough distinct evidence to call it repeated."""
    scan_a, scan_b = uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, observed=True),
        _sample(scan_id=scan_b, sample_index=1, observed=False),
        _sample(scan_id=scan_b, sample_index=2, observed=False),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "emerging"
    assert result.period_count == 2


# ── repeated ──────────────────────────────────────────────────────────────


def test_consistent_samples_within_one_period_is_repeated():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_id, sample_index=2, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_id, sample_index=3, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "repeated"
    assert result.score == 1.0
    assert result.period_count == 1
    assert result.agreement == {
        "brand_presence": 1.0,
        "recommendation_status": 1.0,
        "source_domain_set": 1.0,
        "position_band": 1.0,
    }


def test_repeated_requires_at_least_two_observed_samples_not_just_high_agreement():
    """Guards the emerging/repeated boundary independent of the
    volatile/stable boundary: 1 observed sample can't be 'repeated' no
    matter how trivially it agrees with itself."""
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, observed=True),
        _sample(scan_id=scan_id, sample_index=2, observed=False),
        _sample(scan_id=scan_id, sample_index=3, observed=False),
    ]

    result = stability.calculate_stability(samples)

    assert result.state != "repeated"
    assert result.state == "emerging"


# ── volatile ──────────────────────────────────────────────────────────────


def test_disagreeing_samples_within_one_period_is_volatile():
    # With a 2-valued dimension (seen/not_seen), a 3-sample majority is
    # always >= 2/3 (~0.667, above the 0.6 threshold) — use 4 samples split
    # evenly (2/4 = 0.5) to force a genuine below-threshold disagreement.
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, brand_detected=True),
        _sample(scan_id=scan_id, sample_index=2, brand_detected=True),
        _sample(scan_id=scan_id, sample_index=3, brand_detected=False),
        _sample(scan_id=scan_id, sample_index=4, brand_detected=False),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "volatile"
    assert result.agreement["brand_presence"] < stability.STABILITY_THRESHOLD


def test_disagreeing_position_bands_is_volatile():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, recommendation_position=1),
        _sample(scan_id=scan_id, sample_index=2, recommendation_position=5),
        _sample(scan_id=scan_id, sample_index=3, recommendation_position=None),
    ]

    result = stability.calculate_stability(samples)

    assert result.agreement["position_band"] < 1.0
    assert result.state == "volatile"


def test_score_is_the_minimum_across_dimensions_not_the_average():
    """One badly-disagreeing dimension must be enough to pull the overall
    score down, even if the other three dimensions agree perfectly."""
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_id, sample_index=2, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_id, sample_index=3, brand_detected=True, recommendation_position=9,
                source_domains=["acme.com"]),
    ]

    result = stability.calculate_stability(samples)

    assert result.agreement["brand_presence"] == 1.0
    assert result.agreement["source_domain_set"] == 1.0
    assert result.agreement["position_band"] < 1.0
    assert result.score == result.agreement["position_band"]
    assert result.score == min(result.agreement.values())


# ── stable (cross-period) ────────────────────────────────────────────────


def test_consistent_consensus_across_two_periods_is_stable():
    scan_a, scan_b = uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_a, sample_index=2, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
        _sample(scan_id=scan_b, sample_index=1, brand_detected=True, recommendation_position=2,
                source_domains=["acme.com"]),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "stable"
    assert result.period_count == 2
    assert result.score == 1.0


def test_period_level_consensus_not_pooled_sample_vote():
    """Design decision #3: agreement across periods compares each period's
    OWN consensus answer, not a flat vote over every sample. Period A has 3
    samples saying 'not_seen' (would dominate a pooled vote); period B has
    1 sample saying 'seen'. Per-period consensus is not_seen vs seen — a
    2-period disagreement, which must read as volatile even though a naive
    pooled vote (3 vs 1) would look 75% consistent (>= threshold)."""
    scan_a, scan_b = uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, brand_detected=False),
        _sample(scan_id=scan_a, sample_index=2, brand_detected=False),
        _sample(scan_id=scan_a, sample_index=3, brand_detected=False),
        _sample(scan_id=scan_b, sample_index=1, brand_detected=True),
    ]

    result = stability.calculate_stability(samples)

    assert result.period_count == 2
    assert result.agreement["brand_presence"] == 0.5  # 1 of 2 periods agrees with the modal consensus
    assert result.state == "volatile"


def test_disagreeing_consensus_across_periods_is_volatile_not_stable():
    scan_a, scan_b = uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, recommendation_position=1),
        _sample(scan_id=scan_a, sample_index=2, recommendation_position=1),
        _sample(scan_id=scan_b, sample_index=1, recommendation_position=None),
        _sample(scan_id=scan_b, sample_index=2, recommendation_position=None),
    ]

    result = stability.calculate_stability(samples)

    assert result.state == "volatile"
    assert result.period_count == 2


def test_three_periods_majority_consensus_still_stable_despite_one_outlier():
    scan_a, scan_b, scan_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, brand_detected=True),
        _sample(scan_id=scan_b, sample_index=1, brand_detected=True),
        _sample(scan_id=scan_c, sample_index=1, brand_detected=False),
    ]

    result = stability.calculate_stability(samples)

    assert result.period_count == 3
    assert result.agreement["brand_presence"] == round(2 / 3, 10) or abs(
        result.agreement["brand_presence"] - 2 / 3
    ) < 1e-9
    # 2 of 3 periods agree — below the 0.6 threshold is not this case (2/3
    # ~= 0.667 >= 0.6), so this should read as stable.
    assert result.state == "stable"


def test_unobserved_period_excluded_from_cross_period_consensus():
    """A period where every sample failed (unobserved) must not count as a
    disagreeing period — it contributes no consensus at all, so it's
    dropped from the cross-period comparison rather than voting."""
    scan_a, scan_b, scan_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    samples = [
        _sample(scan_id=scan_a, sample_index=1, brand_detected=True),
        _sample(scan_id=scan_b, sample_index=1, brand_detected=True),
        _sample(scan_id=scan_c, sample_index=1, observed=False),
        _sample(scan_id=scan_c, sample_index=2, observed=False),
    ]

    result = stability.calculate_stability(samples)

    # scan_c contributes no consensus value, leaving 2 real periods that
    # agree perfectly.
    assert result.agreement["brand_presence"] == 1.0
    assert result.state == "stable"


# ── position band boundaries ────────────────────────────────────────────


def test_position_band_boundaries():
    scan_id = uuid.uuid4()
    for position, expected_band in [(1, "1-3"), (3, "1-3"), (4, "4-6"), (6, "4-6"), (7, "7+"), (20, "7+")]:
        samples = [
            _sample(scan_id=scan_id, sample_index=i, recommendation_position=position) for i in range(1, 4)
        ]
        result = stability.calculate_stability(samples)
        assert result.agreement["position_band"] == 1.0
        # all 3 samples share the same position -> same band -> perfect agreement
        # (band itself isn't directly exposed, so we assert indirectly via a
        # mixed-band case below for the actual bucketing boundaries)


def test_position_band_1_3_boundary_vs_4_6_disagreement():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, recommendation_position=3),  # 1-3
        _sample(scan_id=scan_id, sample_index=2, recommendation_position=4),  # 4-6
        _sample(scan_id=scan_id, sample_index=3, recommendation_position=3),  # 1-3
    ]

    result = stability.calculate_stability(samples)

    # 2 of 3 in the "1-3" band -> 2/3 agreement
    assert abs(result.agreement["position_band"] - 2 / 3) < 1e-9


def test_not_found_is_its_own_band_distinct_from_low_position():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, recommendation_position=None),
        _sample(scan_id=scan_id, sample_index=2, recommendation_position=None),
        _sample(scan_id=scan_id, sample_index=3, recommendation_position=1),
    ]

    result = stability.calculate_stability(samples)

    assert abs(result.agreement["position_band"] - 2 / 3) < 1e-9


# ── source_domain_set dimension ─────────────────────────────────────────


def test_source_domain_set_agreement_exact_match():
    scan_id = uuid.uuid4()
    samples = [
        _sample(scan_id=scan_id, sample_index=1, source_domains=["acme.com", "yelp.com"]),
        _sample(scan_id=scan_id, sample_index=2, source_domains=["yelp.com", "acme.com"]),  # same set, different order
        _sample(scan_id=scan_id, sample_index=3, source_domains=["other.com"]),
    ]

    result = stability.calculate_stability(samples)

    # samples 1 and 2 are the same *set* regardless of insertion order
    assert abs(result.agreement["source_domain_set"] - 2 / 3) < 1e-9


def test_empty_source_domain_set_is_a_valid_consistent_value():
    scan_id = uuid.uuid4()
    samples = [_sample(scan_id=scan_id, sample_index=i, source_domains=[]) for i in range(1, 4)]

    result = stability.calculate_stability(samples)

    assert result.agreement["source_domain_set"] == 1.0


# ── QueryStability dataclass shape ──────────────────────────────────────


def test_calculation_version_default():
    scan_id = uuid.uuid4()
    samples = [_sample(scan_id=scan_id, sample_index=i) for i in range(1, 4)]

    result = stability.calculate_stability(samples)

    assert result.calculation_version == "stability_v1"


def test_tracked_query_id_defaults_to_none_for_single_query_calculation():
    result = stability.calculate_stability([])
    assert result.tracked_query_id is None


# ── DB-backed wrappers ────────────────────────────────────────────────────


def _make_client(db) -> Client:
    client = Client(name="Acme Dental", website="https://acme.example", industry="dental clinic")
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _make_scan(db, client) -> Scan:
    scan = Scan(client_id=client.id, platform="chatgpt", status="completed")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _make_tracked_query(db, client, **kwargs) -> TrackedQuery:
    tq = TrackedQuery(
        client_id=client.id,
        text=kwargs.pop("text", "best dental clinic kl"),
        normalized_text=kwargs.pop("normalized_text", "best dental clinic kl"),
        source=kwargs.pop("source", "manual"),
        intent=kwargs.pop("intent", "recommendation"),
        **kwargs,
    )
    db.add(tq)
    db.commit()
    db.refresh(tq)
    return tq


def test_calculate_query_stability_reads_linked_samples(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    tq = _make_tracked_query(db, client)

    for i in range(1, 4):
        db.add(
            ScanQueryResult(
                scan_id=scan.id,
                platform="chatgpt",
                category="recommendation",
                query_text=tq.text,
                response_text="Yes, Acme Dental is a great choice.",
                brand_detected=True,
                recommendation_position=2,
                tracked_query_id=tq.id,
                sample_index=i,
            )
        )
    db.commit()

    result = stability.calculate_query_stability(tq.id, db)

    assert result.sample_count == 3
    assert result.state == "repeated"
    assert result.score == 1.0


def test_calculate_query_stability_ignores_control_rows(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    tq = _make_tracked_query(db, client)

    for i in range(1, 3):
        db.add(
            ScanQueryResult(
                scan_id=scan.id,
                platform="chatgpt",
                category="recommendation",
                query_text=tq.text,
                response_text="Yes.",
                brand_detected=True,
                tracked_query_id=tq.id,
                sample_index=i,
            )
        )
    # A control row happens to carry the same tracked_query_id — must be
    # excluded from the sample count regardless.
    db.add(
        ScanQueryResult(
            scan_id=scan.id,
            platform="chatgpt",
            category="recommendation",
            query_text=tq.text,
            response_text="Yes.",
            brand_detected=True,
            tracked_query_id=tq.id,
            sample_index=3,
            is_control=True,
        )
    )
    db.commit()

    result = stability.calculate_query_stability(tq.id, db)

    assert result.sample_count == 2
    assert result.state == "insufficient"


def test_calculate_query_stability_loads_source_domains(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    tq = _make_tracked_query(db, client)

    result_ids = []
    for i in range(1, 4):
        row = ScanQueryResult(
            scan_id=scan.id,
            platform="chatgpt",
            category="recommendation",
            query_text=tq.text,
            response_text="Yes.",
            brand_detected=True,
            tracked_query_id=tq.id,
            sample_index=i,
        )
        db.add(row)
        db.flush()
        result_ids.append(row.id)
        db.add(
            ScanQuerySource(
                scan_query_result_id=row.id,
                url="https://acme.example/about",
                domain="acme.example",
                rank=1,
            )
        )
    db.commit()

    result = stability.calculate_query_stability(tq.id, db)

    assert result.agreement["source_domain_set"] == 1.0
    assert result.state == "repeated"


def test_calculate_query_stability_no_samples_returns_insufficient(db):
    client = _make_client(db)
    tq = _make_tracked_query(db, client)

    result = stability.calculate_query_stability(tq.id, db)

    assert result.state == "insufficient"
    assert result.sample_count == 0


def test_calculate_portfolio_stability_covers_every_tracked_query(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    tq_with_samples = _make_tracked_query(db, client, text="q1", normalized_text="q1")
    tq_without_samples = _make_tracked_query(db, client, text="q2", normalized_text="q2")

    for i in range(1, 4):
        db.add(
            ScanQueryResult(
                scan_id=scan.id,
                platform="chatgpt",
                category="recommendation",
                query_text=tq_with_samples.text,
                response_text="Yes.",
                brand_detected=True,
                tracked_query_id=tq_with_samples.id,
                sample_index=i,
            )
        )
    db.commit()

    results = stability.calculate_portfolio_stability(client.id, db)
    by_id = {r.tracked_query_id: r for r in results}

    assert len(results) == 2
    assert by_id[tq_with_samples.id].state == "repeated"
    assert by_id[tq_without_samples.id].state == "insufficient"
    assert by_id[tq_without_samples.id].sample_count == 0


def test_calculate_portfolio_stability_scopes_to_client(db):
    client_a = _make_client(db)
    client_b = Client(name="Other Clinic", website="https://other.example", industry="dental clinic")
    db.add(client_b)
    db.commit()
    db.refresh(client_b)

    _make_tracked_query(db, client_a)
    _make_tracked_query(db, client_b)

    results = stability.calculate_portfolio_stability(client_a.id, db)

    assert len(results) == 1


def test_calculate_portfolio_stability_empty_portfolio_returns_empty_list(db):
    client = _make_client(db)

    results = stability.calculate_portfolio_stability(client.id, db)

    assert results == []
