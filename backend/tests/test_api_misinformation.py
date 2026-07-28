"""Misinformation admin API. Fixture style mirrors test_work_log_api.py."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.time import utcnow


@pytest.fixture
def client(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings
    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


def _seed(db, status="suggested"):
    from app.models.client import Client
    from app.models.misinformation_finding import MisinformationFinding
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult

    c = Client(name="Klinik A", website="klinik-a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    r = ScanQueryResult(
        scan_id=s.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?",
        response_text="Klinik A guarantees full recovery for every patient.",
        brand_detected=True, hallucination_flagged=True,
    )
    db.add(r)
    db.commit()
    f = MisinformationFinding(
        client_id=c.id, scan_query_result_id=r.id,
        quote="guarantees full recovery", category="prohibited_claim",
        rule_key="guaranteed_results", severity="high",
        explanation="Outcome guarantee the clinic cannot make.", status=status,
    )
    db.add(f)
    db.commit()
    return c, f


def test_requires_auth(client, db):
    c, _ = _seed(db)
    assert client.get(f"/api/v1/clients/{c.id}/misinformation").status_code in (401, 403)


def test_queue_returns_findings_with_labels_and_counts(client, db, auth_headers):
    c, _ = _seed(db)
    res = client.get(f"/api/v1/clients/{c.id}/misinformation", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["counts"] == {"suggested": 1}
    row = body["findings"][0]
    assert row["quote"] == "guarantees full recovery"
    assert row["category_label"] == "Claim that creates advertising risk"
    assert row["rule_text"] == "Claims guaranteeing treatment outcomes or cure"
    assert row["platform_label"] == "ChatGPT"
    assert row["query_text"] == "Is Klinik A any good?"


def test_unknown_client_and_foreign_finding_404(client, db, auth_headers):
    c, f = _seed(db)
    assert client.get(
        f"/api/v1/clients/{uuid.uuid4()}/misinformation", headers=auth_headers
    ).status_code == 404
    res = client.post(
        f"/api/v1/clients/{uuid.uuid4()}/misinformation/{f.id}/review",
        json={"action": "confirm"}, headers=auth_headers,
    )
    assert res.status_code == 404


def test_review_confirm_then_corrected_then_resolve(client, db, auth_headers):
    from app.models.misinformation_finding import MisinformationFinding
    from app.models.remediation_item import RemediationItem

    c, f = _seed(db)
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/review",
        json={"action": "confirm"}, headers=auth_headers,
    )
    assert res.status_code == 200 and res.json()["status"] == "confirmed"
    assert db.query(RemediationItem).count() == 1

    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/corrected", headers=auth_headers
    )
    assert res.status_code == 200 and res.json()["status"] == "corrected"

    # Resolve is refused until a later scan stops showing the statement.
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/resolve", headers=auth_headers
    )
    assert res.status_code == 409

    db.query(MisinformationFinding).filter_by(id=f.id).one().status = "candidate_fixed"
    db.commit()
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/resolve", headers=auth_headers
    )
    assert res.status_code == 200 and res.json()["status"] == "verified_fixed"


def test_review_rejects_unknown_action(client, db, auth_headers):
    c, f = _seed(db)
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/review",
        json={"action": "approve"}, headers=auth_headers,
    )
    assert res.status_code == 422


def test_corrected_refused_before_confirm(client, db, auth_headers):
    c, f = _seed(db)
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/corrected", headers=auth_headers
    )
    assert res.status_code == 409


def test_review_refused_once_the_finding_left_review(client, db, auth_headers):
    c, f = _seed(db, status="confirmed")
    res = client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/review",
        json={"action": "confirm"}, headers=auth_headers,
    )
    assert res.status_code == 409


def test_spawned_item_never_reaches_any_client_surface(client, db, auth_headers):
    """Spec §4: the client view is unchanged until Premium gating exists. That
    covers the overview counters too, not just the Progress tab — a resolved
    compliance item stamps status=corrected + resolved_at, which is exactly
    what the "fixed this month" counter looks for."""
    from app.models.misinformation_finding import MisinformationFinding
    from app.models.remediation_item import RemediationItem

    c, f = _seed(db)
    client.post(
        f"/api/v1/clients/{c.id}/misinformation/{f.id}/review",
        json={"action": "confirm"}, headers=auth_headers,
    )
    db.query(MisinformationFinding).filter_by(id=f.id).one().status = "candidate_fixed"
    db.commit()
    client.post(f"/api/v1/clients/{c.id}/misinformation/{f.id}/resolve", headers=auth_headers)

    item = db.query(RemediationItem).one()
    assert item.status == "corrected" and item.resolved_at is not None

    c.share_token = "tok_" + "b" * 40
    db.commit()

    assert client.get(f"/api/v1/view/{c.share_token}/progress").json() == []
    overview = client.get(f"/api/v1/view/{c.share_token}/overview").json()
    assert overview["has_progress"] is False
    assert overview["fixed_this_month"] == 0
