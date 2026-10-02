"""Placement engine Task 6: pursue -> Outcome Action, placed and verified proof."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.outcome_action import OutcomeAction
from app.models.placement_target import PlacementTarget
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.models.work_log_entry import WorkLogEntry
from app.services import outcome_action_service, outcome_verification_service
from app.services import placement_service as ps
from tests.auth_helpers import owner_headers

_BASE = datetime(2026, 9, 1)
_URL = "https://klguide.example/best-dentists"
_QUERY = "best dentist in KL"


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme Dental", website="https://acme.com", industry="dentist")
    db.add(c)
    db.commit()
    return c


def _scan(db, client, day):
    s = Scan(id=uuid.uuid4(), client_id=client.id, status="completed",
             completed_at=_BASE + timedelta(days=day))
    db.add(s)
    db.commit()
    return s


def _answer(db, scan, *, seen=False, client_on_page=False):
    sqr = ScanQueryResult(scan_id=scan.id, platform="chatgpt", category="recommendation",
                          query_text=_QUERY, response_text="…", brand_detected=seen,
                          sources_captured=True)
    sqr.sources.append(ScanQuerySource(
        url=_URL, domain="klguide.example", title="10 Best Dentists in KL", rank=1,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": client_on_page, "competitors": []}))
    db.add(sqr)
    db.commit()
    return sqr


def _discovered(db):
    client = _client(db)
    scan = _scan(db, client, 0)
    first_answer = _answer(db, scan)
    ps.refresh_targets(scan.id, client.id, db)
    return client, db.query(PlacementTarget).one(), first_answer


def _publish(db, action, day):
    """What the delivery workflow does: client approval, then publication."""
    action.client_decision = "approved"
    action.client_decided_at = _BASE + timedelta(days=day)
    action.approval_evidence_hash = "x" * 64
    action.status = "published"
    action.published_at = _BASE + timedelta(days=day)
    db.commit()


# ── pursue ──────────────────────────────────────────────────────────────────

def test_pursue_creates_one_delivery_item(db):
    _, t, _ = _discovered(db)

    action = ps.pursue(t, db, due_date=datetime(2026, 10, 15).date())

    assert t.status == "pursuing" and t.outcome_action_id == action.id
    assert action.source_kind == "placement"
    assert action.source_ref == f"placement:{t.id}"
    assert action.action_type == "authority"
    assert action.title == "Get listed on klguide.example"
    assert action.destination_url == _URL
    assert action.due_date.isoformat() == "2026-10-15"
    assert action.priority in {"high", "medium", "low"}
    assert action.client_safe_summary and "cited" not in action.client_safe_summary.lower()

    again = ps.pursue(t, db)
    assert again.id == action.id
    assert db.query(OutcomeAction).count() == 1


@pytest.mark.parametrize("status", ["dismissed", "placed", "verified"])
def test_pursue_only_from_open_or_stale(db, status):
    _, t, _ = _discovered(db)
    t.status = status
    db.commit()
    with pytest.raises(ps.PlacementTransitionError):
        ps.pursue(t, db)


def test_proof_question_is_frozen_once_pursuing(db):
    client, t, first_answer = _discovered(db)
    ps.pursue(t, db)

    later = _scan(db, client, 3)
    _answer(db, later)
    ps.refresh_targets(later.id, client.id, db)

    assert t.representative_result_id == first_answer.id


# ── placed: the page now names the client ───────────────────────────────────

def test_page_naming_the_client_after_publication_marks_it_placed(db):
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)

    later = _scan(db, client, 5)
    _answer(db, later, client_on_page=True)
    ps.refresh_targets(later.id, client.id, db)

    db.refresh(t)
    assert t.status == "placed" and t.placed_at is not None and t.client_present is True
    assert db.query(ActivityLog).filter_by(client_id=client.id, event_type="placement_placed").count() == 1
    entry = db.query(WorkLogEntry).filter_by(client_id=client.id, source_ref=f"placement:{t.id}:placed").one()
    assert entry.status == "suggested" and entry.category == "authority"
    assert "klguide.example" in entry.description
    for banned in ("cited", "mentioned", "citation"):
        assert banned not in entry.description.lower()


def test_unpublished_placement_is_not_marked_placed(db):
    client, t, _ = _discovered(db)
    ps.pursue(t, db)

    later = _scan(db, client, 5)
    _answer(db, later, client_on_page=True)
    ps.refresh_targets(later.id, client.id, db)

    assert t.status == "pursuing" and t.client_present is True


def test_scan_from_before_publication_does_not_count(db):
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    early = _scan(db, client, 1)
    _publish(db, action, day=2)
    _answer(db, early, client_on_page=True)
    ps.refresh_targets(early.id, client.id, db)

    assert t.status == "pursuing"


# ── verified: the proof question now sees the client ────────────────────────

def test_placement_action_resolves_its_proof_question(db):
    client, t, first_answer = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)

    assert outcome_action_service.source_query_result_for_action(action, db).id == first_answer.id


def test_flipped_proof_question_verifies_action_and_target(db):
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)

    later = _scan(db, client, 5)
    _answer(db, later, seen=True, client_on_page=True)
    outcome_verification_service.verify_waiting_actions(later.id, client.id, db)
    ps.refresh_targets(later.id, client.id, db)

    db.refresh(action)
    db.refresh(t)
    assert action.status == "verified"
    assert t.status == "verified"


def test_unflipped_proof_question_leaves_the_placement_placed(db):
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)

    later = _scan(db, client, 5)
    _answer(db, later, seen=False, client_on_page=True)
    outcome_verification_service.verify_waiting_actions(later.id, client.id, db)
    ps.refresh_targets(later.id, client.id, db)

    db.refresh(action)
    db.refresh(t)
    assert action.status == "no_change"
    assert t.status == "placed"  # listed on the page, AI answer not moved yet


def test_scan_runs_placements_after_verification():
    import inspect
    from app.services import scan_service

    source = inspect.getsource(scan_service.run_scan)
    assert source.index("verify_waiting_actions") < source.index("refresh_targets")


# ── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def api(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_pursue_route(api, db):
    client, t, _ = _discovered(db)
    r = api.post(f"/api/v1/clients/{client.id}/placements/{t.id}/pursue",
                 headers=owner_headers(), json={"due_date": "2026-10-15"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pursuing" and body["outcome_action_id"]


def test_pursue_route_rejects_a_dismissed_target(api, db):
    client, t, _ = _discovered(db)
    t.status = "dismissed"
    db.commit()
    r = api.post(f"/api/v1/clients/{client.id}/placements/{t.id}/pursue", headers=owner_headers(), json={})
    assert r.status_code == 409
