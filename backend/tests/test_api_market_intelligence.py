"""API contract for the internal market-intelligence aggregates.

These routes are authenticated and internal in this release: the aggregates are
privacy-safe by construction, but privacy-safe and ready-to-publish are
different bars, and anything public goes through the Task 7 review workflow.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

from tests.test_benchmark_snapshot_service import PERIOD_END, PERIOD_START
from tests.test_market_intelligence_service import population

PERIOD_PARAMS = {"period_start": PERIOD_START.isoformat(), "period_end": PERIOD_END.isoformat()}
ROUTES = ("source-influence", "query-demand", "pack-signals")


@pytest.fixture
def api(db):
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings

    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


@pytest.mark.parametrize("route", ROUTES)
def test_every_route_requires_authentication(api, db, route):
    assert api.get(f"/api/v1/market-intelligence/{route}").status_code in (401, 403)


@pytest.mark.parametrize("route", ROUTES)
def test_every_route_returns_a_list_for_an_empty_portfolio(api, auth_headers, route):
    response = api.get(
        f"/api/v1/market-intelligence/{route}", headers=auth_headers, params=PERIOD_PARAMS
    )
    assert response.status_code == 200
    assert response.json() == []


def test_source_influence_returns_categories_and_bands(api, db, auth_headers):
    population(db, count=6)
    response = api.get(
        "/api/v1/market-intelligence/source-influence",
        headers=auth_headers,
        params=PERIOD_PARAMS,
    )
    assert response.status_code == 200

    social = next(row for row in response.json() if row["domain_category"] == "social")
    assert social["influence_band"] == "leading"
    assert social["contributing_client_band"] == "5–9"
    assert social["suppressed"] is False


def test_query_demand_returns_intent_categories(api, db, auth_headers):
    population(db, count=6)
    response = api.get(
        "/api/v1/market-intelligence/query-demand", headers=auth_headers, params=PERIOD_PARAMS
    )
    assert response.status_code == 200
    assert any(row["intent_category"] == "brand" for row in response.json())


def test_payloads_carry_no_domains_urls_or_identifiers(api, db, auth_headers):
    population(db, count=6, urls=("https://www.facebook.com/identifying-page",))

    for route in ("source-influence", "query-demand"):
        body = api.get(
            f"/api/v1/market-intelligence/{route}", headers=auth_headers, params=PERIOD_PARAMS
        ).json()
        serialized = str(body)
        for forbidden in ("facebook.com", "identifying-page", "http", "client_id", "@"):
            assert forbidden not in serialized, f"{forbidden} leaked from {route}"


def test_suppressed_cells_are_returned_with_a_reason_and_no_bands(api, db, auth_headers):
    population(db, count=3)
    body = api.get(
        "/api/v1/market-intelligence/source-influence",
        headers=auth_headers,
        params=PERIOD_PARAMS,
    ).json()

    assert body
    for row in body:
        assert row["suppressed"] is True
        assert row["suppression_reason"] == "insufficient_contributors"
        assert row["influence_band"] is None
        assert row["observation_band"] is None


def test_pack_signals_are_advisory_only(api, db, auth_headers):
    population(db, count=6)
    body = api.get(
        "/api/v1/market-intelligence/pack-signals", headers=auth_headers, params=PERIOD_PARAMS
    ).json()

    assert body
    assert all(row["requires_human_approval"] is True for row in body)


def test_period_defaults_to_the_last_closed_month(api, db, auth_headers):
    """No dates supplied must not mean "all time" — that would blend periods
    into one undated aggregate."""
    population(db, count=6)
    response = api.get("/api/v1/market-intelligence/source-influence", headers=auth_headers)
    assert response.status_code == 200
    for row in response.json():
        assert row["period_start"] < row["period_end"]
