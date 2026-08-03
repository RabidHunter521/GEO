"""Public truth-health endpoint contract.

This endpoint is reached using only a share token, so these tests assert the
wire whitelist rather than reusing the admin Truth Vault response schemas.
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.api.v1.client_view import _view_rate_limit
    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _account(db):
    from app.models.client import Client

    account = Client(
        name="Acme Dental",
        website="https://acme.example",
        industry="Dental clinic",
        contact_email="hello@acme.example",
        share_token="truth_" + "a" * 40,
    )
    db.add(account)
    db.commit()
    return account


def _approved_version(db, fact, value, *, approved_at, secret="private"):
    from app.models.truth_fact import TruthFactVersion

    version = TruthFactVersion(
        truth_fact_id=fact.id,
        value_json={"value": value, "display_value": "Internal display value"},
        status="approved",
        source_url=f"https://source.example/{secret}",
        reviewer_note=f"reviewer note: {secret}",
        effective_from=approved_at - timedelta(days=1),
        approved_at=approved_at,
        approved_by=f"reviewer-{secret}@example.com",
    )
    db.add(version)
    return version


def _finding(db, account, result, fact, *, status, secret):
    from app.models.misinformation_finding import MisinformationFinding

    finding = MisinformationFinding(
        client_id=account.id,
        scan_query_result_id=result.id,
        truth_fact_id=fact.id,
        truth_fact_version_id=fact.versions[0].id,
        quote=f"Raw AI quote: {secret}",
        category="factual_error",
        severity="high",
        explanation=f"Internal reasoning: {secret}",
        admin_note=f"Admin note: {secret}",
        status=status,
    )
    db.add(finding)


def test_truth_health_exposes_only_current_approved_location_summary_and_reviewed_counts(client, db):
    from app.core.time import utcnow
    from app.models.business_location import BusinessLocation
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.truth_fact import TruthFact, TruthFactVersion

    account = _account(db)
    current_time = utcnow()
    orchard = BusinessLocation(
        client_id=account.id,
        name="Orchard Clinic",
        slug="orchard",
        city="Singapore",
        is_primary=True,
        hours_json={
            "monday": [{"open": "09:00", "close": "17:00"}],
            "tuesday": [{"open": "09:00", "close": "17:00"}],
            "wednesday": [{"open": "09:00", "close": "17:00"}],
            "thursday": [{"open": "09:00", "close": "17:00"}],
            "friday": [{"open": "09:00", "close": "17:00"}],
            "saturday": [],
            "sunday": [],
        },
    )
    inactive = BusinessLocation(
        client_id=account.id,
        name="Private archive location",
        slug="private-archive",
        city="Private city",
        active=False,
    )
    category_fact = TruthFact(
        client_id=account.id,
        fact_type="offering",
        fact_key="service_categories",
    )
    db.add_all([orchard, inactive, category_fact])
    db.flush()
    approved = _approved_version(
        db, category_fact, ["Dental implants", "Emergency care"], approved_at=current_time
    )
    db.add(TruthFactVersion(
        truth_fact_id=category_fact.id,
        value_json={"value": ["DRAFT_SERVICE_SECRET"], "display_value": "Draft"},
        status="draft",
        source_url="https://source.example/draft-secret",
        reviewer_note="draft reviewer note",
        approved_by="draft-reviewer@example.com",
        effective_from=current_time,
    ))
    scan = Scan(client_id=account.id, status="completed", completed_at=current_time)
    db.add(scan)
    db.flush()
    result = ScanQueryResult(
        scan_id=scan.id,
        platform="chatgpt",
        category="brand",
        query_text="private query",
        response_text="private raw response",
    )
    db.add(result)
    db.flush()
    _finding(db, account, result, category_fact, status="confirmed", secret="OPEN_SECRET")
    _finding(db, account, result, category_fact, status="corrected", secret="CORRECTED_SECRET")
    _finding(db, account, result, category_fact, status="suggested", secret="DRAFT_CONFLICT_SECRET")
    db.commit()

    response = client.get(f"/api/v1/view/{account.share_token}/truth-health")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "locations",
        "fact_freshness",
        "reviewed_open_issue_count",
        "corrected_count",
        "open_issues",
        "resolved_issues",
    }
    assert body["fact_freshness"] == current_time.isoformat()
    assert body["reviewed_open_issue_count"] == 1
    assert body["corrected_count"] == 1
    assert body["locations"] == [{
        "name": "Orchard Clinic",
        "city": "Singapore",
        "hours_summary": "Mon–Fri: 09:00–17:00; Sat–Sun: Closed",
        "service_categories": ["Dental implants", "Emergency care"],
    }]
    assert body["open_issues"] == [{
        "summary": "A reviewed AI answer conflicts with verified business information.",
        "status_label": "Open",
    }]
    assert body["resolved_issues"] == [{
        "summary": "A reviewed AI answer conflicts with verified business information.",
        "status_label": "Corrected",
    }]

    serialized = str(body)
    for secret in (
        "DRAFT_SERVICE_SECRET",
        "draft-secret",
        "draft reviewer note",
        "draft-reviewer@example.com",
        "reviewer-private@example.com",
        "Private archive location",
        "Private city",
        "OPEN_SECRET",
        "CORRECTED_SECRET",
        "DRAFT_CONFLICT_SECRET",
        "Internal reasoning",
        "Admin note",
        str(category_fact.id),
        str(approved.id),
    ):
        assert secret not in serialized


def test_truth_health_hides_unreviewed_conflicts_and_returns_404_for_prospects(client, db):
    account = _account(db)
    account.is_prospect = True
    db.commit()

    response = client.get(f"/api/v1/view/{account.share_token}/truth-health")

    assert response.status_code == 404
