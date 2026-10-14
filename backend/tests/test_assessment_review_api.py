"""Review safeguards at the API: no direct score edits, review status,
cross-client reviews-due list, reasons enforced on accept."""
import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import owner_headers


@pytest.fixture
def api(db):
    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _client(db, name="Acme", **kw):
    from app.models.client import Client

    c = Client(name=name, website=f"https://{name.lower()}.example", industry="Dental", **kw)
    db.add(c)
    db.commit()
    return c


def _suggest(db, c, dimension="brand_authority", score=58):
    from app.models.dimension_assessment import DimensionAssessment

    db.add(DimensionAssessment(
        client_id=c.id, dimension=dimension, suggested_score=score,
        evidence_bullets=["Listed on Google with 40 reviews"], status="suggested",
        criteria=[{
            "key": "third_party_coverage", "label": "Coverage", "max": 100, "basis": "judged",
            "points": score, "final_points": None, "evidence": None, "admin_hint": None,
        }],
    ))
    db.commit()


def test_settings_cannot_set_a_reviewed_score_directly(api, db):
    c = _client(db)
    r = api.patch(
        f"/api/v1/clients/{c.id}", headers=owner_headers(),
        json={"brand_authority_score": 90, "brand_authority_evidence": "Trust me"},
    )
    assert r.status_code == 422
    assert "accepting a review" in r.json()["detail"]
    db.refresh(c)
    assert c.brand_authority_score == 0


def test_settings_resending_current_values_is_allowed(api, db):
    c = _client(db)
    r = api.patch(
        f"/api/v1/clients/{c.id}", headers=owner_headers(),
        json={"brand_authority_score": 0, "content_quality_score": 0, "score_drop_threshold": 40},
    )
    assert r.status_code == 200, r.text
    assert r.json()["score_drop_threshold"] == 40


def test_accept_without_reason_for_a_change_is_422(api, db):
    c = _client(db)
    _suggest(db, c)
    url = f"/api/v1/clients/{c.id}/assessments/brand_authority/accept"
    r = api.post(url, headers=owner_headers(), json={"points": {"third_party_coverage": 70}})
    assert r.status_code == 422
    r = api.post(
        url, headers=owner_headers(),
        json={"points": {"third_party_coverage": 70}, "reason": "Two national press features found"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "adjusted"
    assert body["final_score"] == 70
    assert body["criteria"][0]["final_points"] == 70
    assert body["adjustment_reason"] == "Two national press features found"
    assert body["reviewed_by"]


def test_assessment_status_reports_review_state(api, db):
    c = _client(db)
    _suggest(db, c)
    api.post(f"/api/v1/clients/{c.id}/assessments/brand_authority/accept",
             headers=owner_headers(), json={})
    r = api.get(f"/api/v1/clients/{c.id}/assessments/status", headers=owner_headers())
    assert r.status_code == 200, r.text
    by_dim = {row["dimension"]: row for row in r.json()}
    assert by_dim["brand_authority"]["score"] == 58
    assert by_dim["brand_authority"]["review_due"] is False
    assert by_dim["brand_authority"]["evidence"] == ["Listed on Google with 40 reviews"]
    assert by_dim["content_quality"]["review_due"] is True
    assert by_dim["content_quality"]["due_reason"] == "never_reviewed"


def test_reviews_due_lists_active_clients_only(api, db):
    from app.core.time import utcnow

    active = _client(db, name="Active")
    _client(db, name="Prospect", is_prospect=True)
    _client(db, name="Gone", archived_at=utcnow())
    r = api.get("/api/v1/dashboard/assessment-reviews-due", headers=owner_headers())
    assert r.status_code == 200, r.text
    names = {row["client_name"] for row in r.json()}
    assert names == {"Active"}
    assert {row["dimension"] for row in r.json() if row["client_id"] == str(active.id)} == {
        "brand_authority", "content_quality",
    }
