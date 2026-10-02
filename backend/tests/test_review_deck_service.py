"""Tests for review_deck_service — the 90-day review deck / case study PDF.

Uses the in-memory SQLite `db` fixture from conftest.py.
"""
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.conversion_event import ConversionEvent
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.work_log_entry import WorkLogEntry
from app.services import review_deck_service
from app.services.review_deck_service import (
    build_review_deck_html,
    gather_review_deck_data,
    generate_review_deck_pdf,
)

NOW = utcnow()


def _client(db, **kw) -> Client:
    c = Client(
        name="Acme Dental",
        legal_name="Acme Dental Sdn Bhd",
        website="https://www.acmedental.my",
        industry="dental clinic",
        country="Malaysia",
        created_at=NOW - timedelta(days=200),
        **kw,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _scan_with_score(db, client, days_ago, overall, citability, version="v1.4.0", breakdown=None):
    when = NOW - timedelta(days=days_ago)
    s = Scan(client_id=client.id, platform="multi", status="completed", completed_at=when)
    db.add(s)
    db.commit()
    gs = GeoScore(
        client_id=client.id, scan_id=s.id, overall_score=overall, ai_citability=citability,
        score_version=version, computed_at=when, platform_breakdown=breakdown,
    )
    db.add(gs)
    db.commit()
    return s


def _result(db, scan, query, seen, response="x", category="recommendation", platform="chatgpt"):
    db.add(ScanQueryResult(
        scan_id=scan.id, platform=platform, competitor_id=None, category=category,
        query_text=query, response_text=response, brand_detected=seen,
    ))
    db.commit()


def _seed(db):
    client = _client(db)
    db.add(Competitor(client_id=client.id, name="Bright Smile", website="https://brightsmile.my"))
    db.commit()
    base = _scan_with_score(
        db, client, 120, 40.0, 20.0,
        breakdown={"chatgpt": {"visibility": 20.0, "status": "ok"}},
    )
    latest = _scan_with_score(
        db, client, 2, 61.0, 55.0,
        breakdown={"chatgpt": {"visibility": 55.0, "status": "ok"},
                   "gemini": {"visibility": 0.0, "status": "unavailable"}},
    )
    _result(db, base, "best dentist in KL", False)
    _result(
        db, latest, "best dentist in KL", True,
        response=(
            "For family care, Acme Dental is one of the most trusted clinics in Kuala Lumpur, "
            "and many patients compare it with Bright Smile before booking."
        ),
    )
    _result(db, base, "is Acme Dental good", True, category="brand")
    _result(db, latest, "is Acme Dental good", True, category="brand")
    db.add(WorkLogEntry(
        client_id=client.id, category="technical", status="published",
        description="Published robots.txt on acmedental.my allowing AI crawlers for Acme Dental",
        entry_date=(NOW - timedelta(days=30)).date(), published_at=NOW - timedelta(days=30),
    ))
    db.add(WorkLogEntry(
        client_id=client.id, category="content", status="suggested",
        description="Draft row that must never show", entry_date=(NOW - timedelta(days=10)).date(),
    ))
    db.add(ActionRecommendation(
        client_id=client.id, action_text="Add an FAQ page", dimension="content_quality",
        estimated_impact=5.0, status="open",
    ))
    db.commit()
    return client


def test_client_mode_names_client_and_shows_movement(db):
    client = _seed(db)
    data = gather_review_deck_data(client, db, "client")
    assert data.score_then == 40.0 and data.score_now == 61.0
    assert data.comparable is True
    assert data.newly_seen_total == 1
    assert data.work_total == 1  # suggested row excluded
    html = build_review_deck_html(data)
    assert "Acme Dental" in html
    assert "Growth Readiness rose from 40 to 61" in html
    assert "Add an FAQ page" in html
    assert "Draft row that must never show" not in html
    assert "Observed" in html and "Reviewed" in html
    # Unavailable platform renders as a dash, never as 0%.
    assert "Gemini" in html


def test_case_study_mode_withholds_identity(db):
    client = _seed(db)
    data = gather_review_deck_data(client, db, "case_study")
    html = build_review_deck_html(data)
    lowered = html.lower()
    for leak in ("acme dental", "acmedental.my", "sdn bhd", "bright smile"):
        assert leak not in lowered, leak
    assert "A dental clinic business in Malaysia" in html
    assert "Client identity withheld" in html
    assert "the client" in html
    # Case study closes on a SeenBy CTA, not the client's open work.
    assert "Add an FAQ page" not in html
    assert "contact@seenby.my" in html


def test_score_version_change_is_not_narrated_as_movement(db):
    client = _client(db)
    _scan_with_score(db, client, 100, 70.0, 60.0, version="v1.2.0")
    _scan_with_score(db, client, 1, 50.0, 30.0, version="v1.4.0")
    data = gather_review_deck_data(client, db, "client")
    assert data.comparable is False
    html = build_review_deck_html(data)
    assert "not directly comparable" in html
    assert "moved from" not in html and "rose from" not in html


def test_young_client_uses_since_onboarding(db):
    client = _client(db)
    client.created_at = NOW - timedelta(days=40)
    db.commit()
    _scan_with_score(db, client, 39, 30.0, 10.0)
    _scan_with_score(db, client, 1, 45.0, 25.0)
    data = gather_review_deck_data(client, db, "client")
    assert data.since_onboarding is True
    assert data.score_then == 30.0
    assert "Since onboarding" in build_review_deck_html(data)


def test_impact_ladder_keeps_levels_separate(db):
    client = _seed(db)
    for level, value in (("observed", 150000), ("estimated", 900000)):
        db.add(ConversionEvent(
            client_id=client.id, event_type="lead", source="manual", evidence_level=level,
            external_event_id=f"evt-{level}",
            occurred_at=NOW - timedelta(days=5), value_minor=value, currency="MYR",
        ))
    db.commit()
    html = build_review_deck_html(gather_review_deck_data(client, db, "client"))
    assert "MYR 1,500.00" in html and "MYR 9,000.00" in html
    assert "Attributed" in html and "Estimated" in html
    assert "MYR 10,500.00" not in html  # never summed across levels


def test_client_facing_language(db):
    client = _seed(db)
    for mode in ("client", "case_study"):
        html = build_review_deck_html(gather_review_deck_data(client, db, mode)).lower()
        for banned in ("cited", "citation rate", "ranking position", "confidence score",
                       "mentioned", "ai citability", "visibility gap"):
            assert banned not in html, (mode, banned)


def test_no_score_returns_none(db):
    client = _client(db)
    assert gather_review_deck_data(client, db, "client") is None
    assert generate_review_deck_pdf(client.id, db) is None


def test_unknown_mode_rejected(db):
    client = _seed(db)
    with pytest.raises(ValueError):
        gather_review_deck_data(client, db, "public")


def test_prospect_returns_none():
    db = MagicMock()
    client = MagicMock(archived_at=None, is_prospect=True)
    db.get.return_value = client
    assert generate_review_deck_pdf(uuid.uuid4(), db) is None


@pytest.mark.skipif(review_deck_service.weasyprint is None, reason="WeasyPrint not installed")
def test_pdf_renders(db):
    client = _seed(db)
    pdf = generate_review_deck_pdf(client.id, db, "case_study")
    assert pdf[:4] == b"%PDF"


# --- API -----------------------------------------------------------------------

@pytest.fixture
def api(db):
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_requires_auth(api, db):
    client = _seed(db)
    assert api.get(f"/api/v1/clients/{client.id}/reports/review-deck").status_code == 401


def test_api_rejects_unknown_mode(api, db):
    from tests.auth_helpers import owner_headers
    client = _seed(db)
    r = api.get(
        f"/api/v1/clients/{client.id}/reports/review-deck?mode=public", headers=owner_headers()
    )
    assert r.status_code == 422


def test_api_case_study_filename_has_no_client_name(api, db, monkeypatch):
    from tests.auth_helpers import owner_headers
    client = _seed(db)
    monkeypatch.setattr(
        review_deck_service, "generate_review_deck_pdf", lambda *a, **k: b"%PDF-fake"
    )
    r = api.get(
        f"/api/v1/clients/{client.id}/reports/review-deck?mode=case_study",
        headers=owner_headers(),
    )
    assert r.status_code == 200
    assert "Acme" not in r.headers["content-disposition"]
    assert "Case-Study" in r.headers["content-disposition"]
