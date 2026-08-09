"""API contract for the publication workflow and the public index edition.

`GET /public/benchmarks/{slug}` is the only route in SeenBy reachable with no
credential and no share token, so most of these tests are about what it
refuses rather than what it returns.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

from tests.test_benchmark_publication_service import all_required_packs
from tests.test_benchmark_snapshot_service import PERIOD_END, PERIOD_START

SLUG = "sea-ai-visibility-index-2026-07"


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


def draft_body(**overrides):
    body = dict(
        slug=SLUG,
        title="SEA AI Visibility Index",
        edition="2026-07",
        period_start=PERIOD_START.isoformat(),
        period_end=PERIOD_END.isoformat(),
        generated_by="generator@seenby.my",
    )
    body.update(overrides)
    return body


def create_draft(api, auth_headers, **overrides):
    return api.post(
        "/api/v1/benchmarks/publications", headers=auth_headers, json=draft_body(**overrides)
    )


def publish_edition(api, auth_headers, db):
    all_required_packs(db)
    created = create_draft(api, auth_headers)
    assert created.status_code == 201, created.text
    publication_id = created.json()["id"]
    approved = api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/approve",
        headers=auth_headers,
        json={"approved_by": "reviewer@seenby.my"},
    )
    assert approved.status_code == 200, approved.text
    published = api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/publish", headers=auth_headers
    )
    assert published.status_code == 200, published.text
    return publication_id


# --- admin workflow -----------------------------------------------------------


def test_every_workflow_route_requires_authentication(api, db):
    all_required_packs(db)
    assert api.post("/api/v1/benchmarks/publications", json=draft_body()).status_code in (401, 403)
    assert api.get("/api/v1/benchmarks/publications").status_code in (401, 403)

    fake = uuid.uuid4()
    for action in ("approve", "publish", "withdraw"):
        response = api.post(f"/api/v1/benchmarks/publications/{fake}/{action}", json={})
        assert response.status_code in (401, 403), action


def test_self_approval_is_rejected_as_a_conflict(api, db, auth_headers):
    all_required_packs(db)
    publication_id = create_draft(api, auth_headers).json()["id"]

    response = api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/approve",
        headers=auth_headers,
        json={"approved_by": "generator@seenby.my"},
    )
    assert response.status_code == 409
    assert "different actor" in response.json()["detail"]


def test_publishing_an_unapproved_draft_is_a_conflict_not_a_server_error(api, db, auth_headers):
    all_required_packs(db)
    publication_id = create_draft(api, auth_headers).json()["id"]

    response = api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/publish", headers=auth_headers
    )
    assert response.status_code == 409


def test_unknown_publication_is_a_404(api, db, auth_headers):
    response = api.post(
        f"/api/v1/benchmarks/publications/{uuid.uuid4()}/publish", headers=auth_headers
    )
    assert response.status_code == 404


def test_a_slug_must_be_url_safe(api, db, auth_headers):
    all_required_packs(db)
    response = create_draft(api, auth_headers, slug="Not A Slug!")
    assert response.status_code == 422


# --- public endpoint ----------------------------------------------------------


def test_published_edition_is_readable_without_any_credential(api, db, auth_headers):
    publish_edition(api, auth_headers, db)

    response = api.get(f"/api/v1/public/benchmarks/{SLUG}")
    assert response.status_code == 200

    body = response.json()
    assert body["slug"] == SLUG
    assert body["payload"]["cohorts"]
    assert body["payload_hash"]


def test_public_payload_carries_no_identifiers_or_internal_fields(api, db, auth_headers):
    publish_edition(api, auth_headers, db)
    body = api.get(f"/api/v1/public/benchmarks/{SLUG}").json()

    serialized = str(body)
    for forbidden in (
        "generated_by",
        "approved_by",
        "generator@seenby.my",
        "reviewer@seenby.my",
        "cohort_key",
        "cohort_id",
        "client_id",
        "contributing_member_count",
        "eligible_member_count",
        "status",
    ):
        assert forbidden not in serialized, f"{forbidden} leaked to the public endpoint"


def test_public_endpoint_asks_not_to_be_indexed(api, db, auth_headers):
    publish_edition(api, auth_headers, db)
    response = api.get(f"/api/v1/public/benchmarks/{SLUG}")
    assert "noindex" in response.headers.get("X-Robots-Tag", "")


def test_an_unpublished_draft_is_not_publicly_readable(api, db, auth_headers):
    all_required_packs(db)
    create_draft(api, auth_headers)
    assert api.get(f"/api/v1/public/benchmarks/{SLUG}").status_code == 404


def test_an_approved_but_unpublished_edition_is_not_publicly_readable(api, db, auth_headers):
    all_required_packs(db)
    publication_id = create_draft(api, auth_headers).json()["id"]
    api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/approve",
        headers=auth_headers,
        json={"approved_by": "reviewer@seenby.my"},
    )
    assert api.get(f"/api/v1/public/benchmarks/{SLUG}").status_code == 404


def test_withdrawal_closes_public_access_immediately(api, db, auth_headers):
    publication_id = publish_edition(api, auth_headers, db)
    assert api.get(f"/api/v1/public/benchmarks/{SLUG}").status_code == 200

    withdrawn = api.post(
        f"/api/v1/benchmarks/publications/{publication_id}/withdraw",
        headers=auth_headers,
        json={"reason": "figures restated"},
    )
    assert withdrawn.status_code == 200

    assert api.get(f"/api/v1/public/benchmarks/{SLUG}").status_code == 404
    # The audit record survives the withdrawal.
    listed = api.get("/api/v1/benchmarks/publications", headers=auth_headers).json()
    assert listed[0]["status"] == "withdrawn"
    assert listed[0]["withdrawn_reason"] == "figures restated"


def test_unknown_slug_returns_the_same_404_as_a_withheld_one(api, db, auth_headers):
    all_required_packs(db)
    create_draft(api, auth_headers)

    unknown = api.get("/api/v1/public/benchmarks/no-such-edition")
    unpublished = api.get(f"/api/v1/public/benchmarks/{SLUG}")

    assert unknown.status_code == unpublished.status_code == 404
    assert unknown.json() == unpublished.json()
