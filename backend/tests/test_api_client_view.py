"""Tests for the read-only client view /overview endpoint.

Fixture approach: seeds real rows into the in-memory SQLite `db` fixture from
conftest.py, overrides get_db and _view_rate_limit on the FastAPI app, then
uses TestClient — mirrors the pattern in test_api_scans.py.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_client(db, *, is_prospect=False, name="Acme Dental"):
    from app.models.client import Client
    c = Client(
        id=uuid.uuid4(),
        name=name,
        website="https://acmedental.com",
        industry="Dental",
        share_token=uuid.uuid4().hex,  # unique 32-char hex token per client
        scan_cadence_days=30,
        is_prospect=is_prospect,
    )
    db.add(c)
    db.flush()
    return c


def _make_scan(db, client_id):
    from app.models.scan import Scan
    s = Scan(
        id=uuid.uuid4(),
        client_id=client_id,
        status="completed",
        triggered_at=datetime(2026, 6, 1),
        completed_at=datetime(2026, 6, 1, 1),
    )
    db.add(s)
    db.flush()
    return s


def _make_result(db, scan_id, *, brand_detected=True, response_text, category="recommendation"):
    from app.models.scan_query_result import ScanQueryResult
    r = ScanQueryResult(
        id=uuid.uuid4(),
        scan_id=scan_id,
        platform="gemini",
        competitor_id=None,
        category=category,
        query_text="best dental clinic in KL",
        response_text=response_text,
        brand_detected=brand_detected,
        hallucination_flagged=False,
    )
    db.add(r)
    db.flush()
    return r


def _make_geo_score(db, client_id, scan_id):
    from app.models.geo_score import GeoScore
    g = GeoScore(
        id=uuid.uuid4(),
        client_id=client_id,
        scan_id=scan_id,
        overall_score=72.0,
        ai_citability=80.0,
        brand_authority=65.0,
        content_quality=60.0,
        technical_foundations=70.0,
        structured_data=55.0,
        computed_at=datetime(2026, 6, 1, 2),
    )
    db.add(g)
    db.flush()
    return g


def _build_test_client(db):
    """Return a FastAPI TestClient with get_db and rate-limit overridden."""
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    tc = TestClient(app)
    return tc


# ── tests ─────────────────────────────────────────────────────────────────────

def test_overview_includes_proof_cards_for_client(db):
    """Non-prospect overview must carry ≥1 proof card with the whitelisted keys."""
    client = _make_client(db, is_prospect=False, name="Acme Dental")
    scan = _make_scan(db, client.id)
    _make_result(
        db, scan.id,
        brand_detected=True,
        response_text="Acme Dental is the top recommended clinic in KL.",
        category="recommendation",
    )
    _make_geo_score(db, client.id, scan.id)
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        body = res.json()
        assert "proof_cards" in body, "proof_cards key missing from overview response"
        assert len(body["proof_cards"]) >= 1, "Expected at least one proof card"
        card = body["proof_cards"][0]
        assert card["kind"] in ("win", "loss")
        assert set(card.keys()) == {"kind", "platform_label", "category", "excerpt"}
        assert "response_text" not in card  # whitelist guard
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_overview_proof_cards_empty_for_prospect(db):
    """Prospect overview must return proof_cards == [] (no proof in a pitch view)."""
    client = _make_client(db, is_prospect=True, name="Prospect Co")
    scan = _make_scan(db, client.id)
    _make_result(
        db, scan.id,
        brand_detected=True,
        response_text="Prospect Co is well-regarded in the industry.",
        category="recommendation",
    )
    _make_geo_score(db, client.id, scan.id)
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("proof_cards") == [], f"Expected [], got {body.get('proof_cards')}"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_overview_proof_cards_empty_non_prospect_no_scan(db):
    """Non-prospect with GeoScore but no ScanQueryResult rows must return proof_cards == []."""
    client = _make_client(db, is_prospect=False, name="No Results Client")
    scan = _make_scan(db, client.id)
    # Create GeoScore but no ScanQueryResult rows for this scan
    _make_geo_score(db, client.id, scan.id)
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("proof_cards") == [], f"Expected [], got {body.get('proof_cards')}"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


# ── fixtures for Task 4 ───────────────────────────────────────────────────────

class _SeedResult:
    """Lightweight container so the fixture can return both client and token."""
    def __init__(self, share_token):
        self.share_token = share_token


@pytest.fixture
def seed_client_with_win_scan(db):
    """Seed a non-prospect client with a completed scan containing one win result."""
    from app.models.scan_query_result import ScanQueryResult

    client = _make_client(db, is_prospect=False, name="WinClient")
    # Give it a unique share token so it never collides with other tests
    client.share_token = uuid.uuid4().hex
    db.flush()

    scan = _make_scan(db, client.id)
    _make_geo_score(db, client.id, scan.id)

    # Seed one result that should produce a "win" excerpt
    result = ScanQueryResult(
        id=uuid.uuid4(),
        scan_id=scan.id,
        platform="chatgpt",
        competitor_id=None,
        category="recommendation",
        query_text="best dental clinic in KL",
        response_text="WinClient is the top recommended dental clinic in KL.",
        brand_detected=True,
        hallucination_flagged=False,
    )
    db.add(result)
    db.commit()
    return _SeedResult(client.share_token)


@pytest.fixture
def http_client(db, seed_client_with_win_scan):
    """TestClient with DB and rate-limit overridden, cleaned up after.

    The seed_client_with_win_scan parameter is used for side-effect only
    (seeding test data); the fixture itself is not used in the body.
    """
    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    yield tc
    app.dependency_overrides.clear()
    app.dependency_overrides.update(_saved)


# ── Task 4 tests ──────────────────────────────────────────────────────────────

def test_scan_result_carries_excerpt(http_client, seed_client_with_win_scan):
    token = seed_client_with_win_scan.share_token
    body = http_client.get(f"/api/v1/view/{token}/scan").json()
    seen = [r for r in body["results"] if r["seen_by_ai"]]
    assert seen and seen[0]["excerpt"]
    assert seen[0]["excerpt_kind"] in ("win", "loss")
    assert "response_text" not in seen[0]  # whitelist guard


def test_scan_excerpt_gated_for_prospect(db):
    """Prospect scan results must always have excerpt=None and excerpt_kind=None,
    even for brand_detected=True recommendation rows that would produce a win excerpt
    for a converted client."""
    client = _make_client(db, is_prospect=True, name="Prospect Dental")
    client.share_token = uuid.uuid4().hex
    db.flush()

    scan = _make_scan(db, client.id)
    _make_geo_score(db, client.id, scan.id)

    # Seed a result that would produce a "win" excerpt for a non-prospect
    _make_result(
        db, scan.id,
        brand_detected=True,
        response_text="Prospect Dental is the top recommended clinic in KL.",
        category="recommendation",
    )
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/scan")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["results"], "Expected at least one scan result"
        for row in body["results"]:
            assert row["excerpt"] is None, f"Expected excerpt=None for prospect, got {row['excerpt']!r}"
            assert row["excerpt_kind"] is None, f"Expected excerpt_kind=None for prospect, got {row['excerpt_kind']!r}"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_overview_traffic_value_includes_at_risk(db):
    """Overview traffic_value must include at-risk fields when avg_deal_value_rm is set,
    a GeoScore exists (to derive visibility_frequency), and a traffic snapshot exists."""
    from app.models.ai_traffic_snapshot import AiTrafficSnapshot
    from datetime import date

    client = _make_client(db, is_prospect=False, name="AtRiskClient")
    client.share_token = uuid.uuid4().hex
    client.avg_deal_value_rm = 1000
    db.flush()

    scan = _make_scan(db, client.id)
    # GeoScore with ai_citability=40 → vis_f = 0.40
    from app.models.geo_score import GeoScore
    g = GeoScore(
        id=uuid.uuid4(),
        client_id=client.id,
        scan_id=scan.id,
        overall_score=50.0,
        ai_citability=40.0,
        brand_authority=50.0,
        content_quality=50.0,
        technical_foundations=50.0,
        structured_data=50.0,
        computed_at=datetime(2026, 6, 1, 2),
    )
    db.add(g)

    snap = AiTrafficSnapshot(
        id=uuid.uuid4(),
        client_id=client.id,
        period=date(2026, 6, 1),
        ai_visitors=100,
    )
    db.add(snap)
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        tv = res.json()["traffic_value"]
        assert tv is not None, "traffic_value should be present"
        assert tv["est_pipeline_rm"] is not None, "captured pipeline should be present"
        assert tv["at_risk_pipeline_rm"] is not None, "at_risk_pipeline_rm should be present"
        assert tv["at_risk_leads"] is not None, "at_risk_leads should be present"
        assert tv["at_risk_won_rm"] is not None, "at_risk_won_rm should be present"
        # at-risk values must be positive (there is a visibility gap at 40%)
        assert tv["at_risk_pipeline_rm"] > 0, "at_risk_pipeline_rm should be > 0 given a visibility gap"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_competitors_includes_headline_battle(db):
    """Non-prospect client with a lost recommendation query naming a competitor
    must include headline_battle in the /competitors response."""
    from app.models.scan_query_result import ScanQueryResult
    from app.models.competitor import Competitor

    client = _make_client(db, is_prospect=False, name="BattleClient")
    client.share_token = uuid.uuid4().hex
    db.flush()

    scan = _make_scan(db, client.id)
    _make_geo_score(db, client.id, scan.id)

    # Seed a competitor named RivalCo
    rival = Competitor(
        id=uuid.uuid4(),
        client_id=client.id,
        name="RivalCo",
        website="https://rivalco.com",
    )
    db.add(rival)
    db.flush()

    # Seed a lost recommendation result — client NOT seen, competitor IS in response_text
    lost_result = ScanQueryResult(
        id=uuid.uuid4(),
        scan_id=scan.id,
        platform="chatgpt",
        competitor_id=None,
        category="recommendation",
        query_text="best dental clinic in KL",
        response_text="RivalCo is the top recommended dental clinic in KL.",
        brand_detected=False,
        hallucination_flagged=False,
    )
    db.add(lost_result)
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/competitors")
        assert res.status_code == 200, res.text
        hb = res.json()["headline_battle"]
        assert hb is not None
        assert hb["rival_name"] == "RivalCo"
        assert hb["query_text"]
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_scan_unseen_result_has_null_excerpt(db):
    """ScanQueryResult with brand_detected=False should serialize with null excerpt."""
    client = _make_client(db, is_prospect=False, name="NullExcerptClient")
    client.share_token = uuid.uuid4().hex
    db.flush()

    scan = _make_scan(db, client.id)
    _make_geo_score(db, client.id, scan.id)

    # Seed an unseen result (brand_detected=False, brand category, no competitor)
    _make_result(
        db, scan.id,
        brand_detected=False,
        response_text="Some response that doesn't mention the client.",
        category="brand",
    )
    db.commit()

    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/scan")
        assert res.status_code == 200, res.text
        body = res.json()
        unseen = [r for r in body["results"] if not r["seen_by_ai"]]
        assert unseen, "Expected at least one unseen result"
        assert unseen[0]["excerpt"] is None, f"Expected excerpt=None, got {unseen[0]['excerpt']}"
        assert unseen[0]["excerpt_kind"] is None, f"Expected excerpt_kind=None, got {unseen[0]['excerpt_kind']}"
        assert "response_text" not in unseen[0]  # whitelist guard
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)
