"""API contract for cohort benchmark comparisons (Phase 6 Task 4).

- Admin `GET /clients/{client_id}/benchmarks` — authenticated, admin shape.
- Share-link `GET /view/{token}/benchmarks` — token-gated, whitelisted shape.

The share-link assertions are the load-bearing ones: that route is reachable by
anyone holding a URL, so what it omits matters more than what it returns.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_snapshot_service import generate_ladder_snapshots

from tests.test_benchmark_comparison_service import APPROVED_AT
from tests.test_benchmark_snapshot_service import (
    PERIOD_END,
    PERIOD_START,
    build_population,
    make_measured_client,
    spec_for,
)

PERIOD_PARAMS = {"period_start": PERIOD_START.isoformat(), "period_end": PERIOD_END.isoformat()}


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


def published_cohort_with_subject(db, *, subject_score=95.0, share=True):
    build_population(db, [float(n) for n in range(10, 110, 10)])
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    for snapshot in generate_ladder_snapshots(
        db, spec_for(), members, "ai_presence_score", PERIOD_START, PERIOD_END
    ):
        if not snapshot.suppressed:
            snapshot.approved_at = APPROVED_AT
    db.commit()

    subject = make_measured_client(db, ai_citability=subject_score)
    if share:
        subject.share_token = uuid.uuid4().hex
        db.commit()
    return subject


# --- admin endpoint -----------------------------------------------------------


def test_admin_endpoint_requires_authentication(api, db):
    subject = published_cohort_with_subject(db)
    assert api.get(f"/api/v1/clients/{subject.id}/benchmarks").status_code in (401, 403)


def test_admin_endpoint_404s_for_unknown_client(api, auth_headers):
    response = api.get(f"/api/v1/clients/{uuid.uuid4()}/benchmarks", headers=auth_headers)
    assert response.status_code == 404


def test_admin_endpoint_returns_the_admin_shape(api, db, auth_headers):
    subject = published_cohort_with_subject(db)
    response = api.get(
        f"/api/v1/clients/{subject.id}/benchmarks", headers=auth_headers, params=PERIOD_PARAMS
    )
    assert response.status_code == 200

    presence = next(r for r in response.json() if r["metric_key"] == "ai_presence_score")
    assert presence["percentile_band"] == "top_quartile"
    assert presence["cohort_key"]
    assert presence["contributing_member_count"] == 10


def test_admin_endpoint_accepts_no_cohort_filter(api, db, auth_headers):
    """A caller-chosen cohort filter is how a differencing attack starts, so
    the parameter must not exist — an attempt to pass one is ignored, never
    honoured."""
    subject = published_cohort_with_subject(db)
    response = api.get(
        f"/api/v1/clients/{subject.id}/benchmarks",
        headers=auth_headers,
        params={**PERIOD_PARAMS, "cohort_key": "healthcare|dental|MY|*|single_location|deep|month"},
    )
    assert response.status_code == 200
    presence = next(r for r in response.json() if r["metric_key"] == "ai_presence_score")
    assert presence["cohort_key"] == spec_for().cohort_key


# --- share-link endpoint ------------------------------------------------------


def test_share_link_endpoint_returns_the_public_shape(api, db):
    subject = published_cohort_with_subject(db)
    response = api.get(f"/api/v1/view/{subject.share_token}/benchmarks", params=PERIOD_PARAMS)
    assert response.status_code == 200

    presence = next(r for r in response.json() if r["metric_key"] == "ai_presence_score")
    assert presence["percentile_band"] == "top_quartile"
    assert presence["member_count_band"] == "10–19"
    assert presence["metric_label"] == "Seen by AI"


def test_share_link_payload_omits_every_internal_field(api, db):
    subject = published_cohort_with_subject(db)
    payload = api.get(
        f"/api/v1/view/{subject.share_token}/benchmarks", params=PERIOD_PARAMS
    ).json()

    serialized = str(payload)
    for forbidden in (
        "cohort_key",
        "cohort_id",
        "eligible_member_count",
        "contributing_member_count",
        "suppression_reason",
        "client_id",
    ):
        assert forbidden not in serialized, f"{forbidden} leaked to the share link"


def test_share_link_never_exposes_an_exact_member_count(api, db):
    subject = published_cohort_with_subject(db)
    payload = api.get(
        f"/api/v1/view/{subject.share_token}/benchmarks", params=PERIOD_PARAMS
    ).json()

    presence = next(r for r in payload if r["metric_key"] == "ai_presence_score")

    # The cohort really has 10 contributors. The client sees the band it falls
    # in, and no field carries the count itself.
    assert presence["member_count_band"] == "10–19"
    assert not any("count" in key for key in presence if key != "member_count_band")
    assert 10 not in [value for value in presence.values() if isinstance(value, int)]


def test_share_link_404s_on_an_invalid_token(api, db):
    published_cohort_with_subject(db)
    assert api.get("/api/v1/view/not-a-real-token/benchmarks").status_code == 404


def test_share_link_suppression_reads_as_missing_data_not_bad_performance(api, db):
    subject = published_cohort_with_subject(db)
    subject.benchmark_opt_out = True
    db.commit()

    payload = api.get(
        f"/api/v1/view/{subject.share_token}/benchmarks", params=PERIOD_PARAMS
    ).json()
    presence = next(r for r in payload if r["metric_key"] == "ai_presence_score")

    assert presence["suppressed"] is True
    assert presence["p50"] is None
    assert presence["percentile_band"] is None
    assert "not yet included" in presence["suppression_message"]
