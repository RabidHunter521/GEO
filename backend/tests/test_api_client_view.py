"""Tests for the read-only client view /overview endpoint.

Fixture approach: seeds real rows into the in-memory SQLite `db` fixture from
conftest.py, overrides get_db and _view_rate_limit on the FastAPI app, then
uses TestClient — mirrors the pattern in test_api_scans.py.
"""
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_client(db, *, is_prospect=False, name="Acme Dental"):
    from app.models.client import Client
    c = Client(
        id=uuid.uuid4(),
        name=name,
        website="https://acmedental.com",
        industry="Dental",
        share_token="a" * 32,  # 32-char token satisfies the 20-64 length check
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
    from app.main import app
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
        from app.main import app
        app.dependency_overrides.clear()


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

    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("proof_cards") == [], f"Expected [], got {body.get('proof_cards')}"
    finally:
        from app.main import app
        app.dependency_overrides.clear()
