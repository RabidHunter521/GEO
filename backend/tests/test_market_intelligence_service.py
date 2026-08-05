"""Phase 6 Task 8 — aggregate source and demand intelligence.

The threat model here is different from the snapshot one. These aggregates
group by category rather than by client, so the risk is not a leaked identifier
but a cell that is really one business: a category where a single client
supplies most of the observations describes that client, not the market.
"""
from datetime import date, datetime

import pytest

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.models.tracked_query import TrackedQuery
from app.schemas.market_intelligence import (
    contributor_band,
    observation_band,
    share_band,
)
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.market_intelligence_service import (
    MAX_SINGLE_CLIENT_SHARE,
    classify_domain_category,
    export_pack_signals,
    query_demand,
    source_influence,
)

from tests.test_benchmark_snapshot_service import (
    PERIOD_END,
    PERIOD_START,
    MID_PERIOD,
    make_measured_client,
)

OUTSIDE_PERIOD = datetime(2026, 5, 15, 12, 0, 0)


def add_sources(db, client, urls, observed_at=MID_PERIOD):
    """Attach source rows to one new result for this client."""
    scan = Scan(client_id=client.id, status="completed", completed_at=observed_at)
    db.add(scan)
    db.commit()
    result = ScanQueryResult(
        scan_id=scan.id,
        platform="chatgpt",
        category="brand",
        query_text="who is best",
        observed_at=observed_at,
        response_text="answer",
    )
    db.add(result)
    db.commit()
    for rank, url in enumerate(urls, start=1):
        db.add(
            ScanQuerySource(
                scan_query_result_id=result.id,
                url=url,
                domain=url.split("//")[-1].split("/")[0],
                rank=rank,
            )
        )
    db.commit()


def population(db, count=6, *, urls=("https://www.facebook.com/x",)):
    clients = [make_measured_client(db, ai_citability=50.0) for _ in range(count)]
    for client in clients:
        add_sources(db, client, list(urls))
    return clients


def members(db):
    return eligible_members_for_period(db, PERIOD_START, PERIOD_END)


# --- banding and classification -----------------------------------------------


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("facebook.com", "social"),
        ("www.instagram.com", "social"),
        ("trustpilot.com", "review"),
        ("shopee.com.my", "marketplace"),
        ("moh.gov.my", "government"),
        ("en.wikipedia.org", "reference"),
        ("thestar.com.my", "news"),
        ("some-clinic.example", "other"),
        ("", "other"),
    ],
)
def test_domain_categories(domain, expected):
    assert classify_domain_category(domain) == expected


def test_unknown_host_is_other_not_a_guess():
    """A wrong bucket would misstate where a client's visibility comes from."""
    assert classify_domain_category("totally-unknown-host.xyz") == "other"


@pytest.mark.parametrize(
    "share,expected",
    [(0.40, "leading"), (0.25, "leading"), (0.12, "high"), (0.05, "moderate"), (0.001, "low")],
)
def test_share_bands(share, expected):
    assert share_band(share) == expected


def test_volume_bands_are_ranges_not_counts():
    assert observation_band(12) == "under_50"
    assert observation_band(120) == "50_199"
    assert observation_band(5000) == "1000_plus"
    assert contributor_band(6) == "5–9"
    assert contributor_band(25) == "20–49"


# --- suppression --------------------------------------------------------------


def test_cell_with_too_few_contributors_is_suppressed(db):
    population(db, count=3)
    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))

    assert rows
    assert all(row.suppressed for row in rows)
    assert {row.suppression_reason for row in rows} == {"insufficient_contributors"}
    assert all(row.influence_band is None for row in rows)


def test_cell_dominated_by_one_client_is_suppressed(db):
    """A category where one business supplies most observations describes that
    business, not the market."""
    clients = population(db, count=6)
    # One client floods the social category.
    for _ in range(40):
        add_sources(db, clients[0], ["https://www.facebook.com/flood"])

    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))
    social = next(row for row in rows if row.domain_category == "social")

    assert social.suppressed is True
    assert social.suppression_reason == "dominant_client"
    assert social.influence_band is None
    assert social.observation_band is None


def test_a_balanced_cell_publishes_bands(db):
    population(db, count=6)
    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))
    social = next(row for row in rows if row.domain_category == "social")

    assert social.suppressed is False
    assert social.influence_band == "leading"
    assert social.observation_band == "under_50"
    assert social.contributing_client_band == "5–9"


def test_dominance_threshold_is_twenty_percent(db):
    assert MAX_SINGLE_CLIENT_SHARE == 0.20


def test_opted_out_clients_never_reach_the_aggregate(db):
    clients = population(db, count=6)
    clients[0].benchmark_opt_out = True
    db.commit()

    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))
    social = next(row for row in rows if row.domain_category == "social")
    # Five contributors remain, which is exactly the floor.
    assert social.suppressed is False
    assert social.contributing_client_band == "5–9"


# --- no raw values ------------------------------------------------------------


def test_no_domain_or_url_appears_in_the_output(db):
    population(db, count=6, urls=("https://www.facebook.com/a-very-identifying-page",))
    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))

    serialized = str([row.model_dump() for row in rows])
    for forbidden in ("facebook.com", "a-very-identifying-page", "http"):
        assert forbidden not in serialized


def test_no_raw_prompt_text_appears_in_the_output(db):
    population(db, count=6)
    rows = query_demand(db, PERIOD_START, PERIOD_END, members(db))

    serialized = str([row.model_dump() for row in rows])
    assert "who is best" not in serialized
    assert "q0" not in serialized


def test_no_exact_counts_appear_in_the_output(db):
    population(db, count=6)
    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))

    for row in rows:
        dumped = row.model_dump()
        # bool is a subclass of int, so `suppressed` has to be excluded
        # explicitly — otherwise this assertion passes for the wrong reason.
        numeric = {
            key: value
            for key, value in dumped.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        assert numeric == {}, f"numeric value leaked: {numeric}"
        assert not any(key.endswith("_count") for key in dumped)


# --- windows ------------------------------------------------------------------


def test_observations_outside_the_window_are_excluded(db):
    clients = population(db, count=6)
    for client in clients:
        add_sources(db, client, ["https://trustpilot.com/x"], observed_at=OUTSIDE_PERIOD)

    rows = source_influence(db, PERIOD_START, PERIOD_END, members(db))
    assert not any(row.domain_category == "review" for row in rows)


def test_a_different_window_is_a_different_reading(db):
    """Seasonal comparison: the same clients over two windows must not return
    the same aggregate by accident."""
    clients = population(db, count=6)
    for client in clients:
        add_sources(db, client, ["https://trustpilot.com/x"], observed_at=OUTSIDE_PERIOD)

    in_period = source_influence(db, PERIOD_START, PERIOD_END, members(db))
    earlier = source_influence(
        db,
        date(2026, 5, 1),
        date(2026, 5, 31),
        eligible_members_for_period(db, date(2026, 5, 1), date(2026, 5, 31)),
    )
    assert {row.domain_category for row in in_period} != {row.domain_category for row in earlier}


# --- demand -------------------------------------------------------------------


def test_query_demand_reports_intent_categories(db):
    population(db, count=6)
    rows = query_demand(db, PERIOD_START, PERIOD_END, members(db))

    assert rows
    brand = next(row for row in rows if row.intent_category == "brand")
    assert brand.suppressed is False
    assert brand.demand_band == "leading"


def test_query_demand_counts_queries_not_repeat_samples(db):
    """Repeat sampling measures the same question again; counting observations
    would inflate whichever intent happens to be sampled most."""
    clients = population(db, count=6)
    tracked = db.query(TrackedQuery).filter(TrackedQuery.client_id == clients[0].id).first()
    scan = Scan(client_id=clients[0].id, status="completed", completed_at=MID_PERIOD)
    db.add(scan)
    db.commit()
    for sample_index in range(2, 12):
        db.add(
            ScanQueryResult(
                scan_id=scan.id,
                platform="chatgpt",
                category="brand",
                query_text=tracked.text,
                tracked_query_id=tracked.id,
                sample_index=sample_index,
                observed_at=MID_PERIOD,
                response_text="answer",
            )
        )
    db.commit()

    rows = query_demand(db, PERIOD_START, PERIOD_END, members(db))
    brand = next(row for row in rows if row.intent_category == "brand")
    # Ten extra samples of one existing query must not tip the cell into
    # single-client dominance.
    assert brand.suppressed is False


# --- pack feedback ------------------------------------------------------------


def test_pack_signals_are_candidates_that_require_approval(db):
    population(db, count=6)
    candidates = export_pack_signals(db, PERIOD_START, PERIOD_END)

    assert candidates
    assert all(candidate.requires_human_approval for candidate in candidates)
    assert all(candidate.band in ("leading", "high") for candidate in candidates)


def test_pack_signals_never_mutate_the_registry(db):
    """Benchmark output describes the market; it must not rewrite the product."""
    from app.industry_packs import registry

    before = {key: registry.get_pack_version(key) for key in registry.registered_keys()}
    population(db, count=6)
    export_pack_signals(db, PERIOD_START, PERIOD_END)
    after = {key: registry.get_pack_version(key) for key in registry.registered_keys()}

    assert before == after


def test_suppressed_cells_produce_no_pack_signals(db):
    population(db, count=3)
    assert export_pack_signals(db, PERIOD_START, PERIOD_END) == []


def test_empty_population_returns_nothing_rather_than_failing(db):
    assert source_influence(db, PERIOD_START, PERIOD_END, []) == []
    assert query_demand(db, PERIOD_START, PERIOD_END, []) == []
