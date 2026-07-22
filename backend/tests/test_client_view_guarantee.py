"""Client-view collapse rule for the commitment block: clients see neutral
states only — at_risk renders as "in_progress", deadline_passed is hidden
until the admin resolves, void is hidden, missed shows only post-resolution."""
import uuid
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee
from app.models.scan import Scan


def _make_client(db):
    c = Client(
        id=uuid.uuid4(), name="Acme Dental", website="https://acmedental.com",
        industry="Dental", share_token=uuid.uuid4().hex, scan_cadence_days=30,
        is_prospect=False,
    )
    db.add(c)
    db.flush()
    s = Scan(id=uuid.uuid4(), client_id=c.id, status="completed",
             triggered_at=datetime(2026, 6, 1), completed_at=datetime(2026, 6, 1, 1))
    db.add(s)
    db.flush()
    db.add(GeoScore(client_id=c.id, scan_id=s.id, ai_citability=45.0,
                    brand_authority=0.0, content_quality=0.0,
                    technical_foundations=0.0, structured_data=0.0,
                    overall_score=45.0, computed_at=datetime(2026, 6, 1, 2)))
    db.flush()
    return c


def _guarantee(db, client, *, start_days_ago=45, deadline_in=45, status="active",
               target=60, resolved=False):
    g = Guarantee(
        client_id=client.id, metric="ai_citability", baseline_value=45,
        target_value=target,
        start_date=date.today() - timedelta(days=start_days_ago),
        deadline_date=date.today() + timedelta(days=deadline_in),
        status=status,
        resolved_at=datetime.utcnow() if resolved else None,
        admin_note="internal note" if resolved else None,
    )
    db.add(g)
    db.flush()
    return g


def _overview(db, client):
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    try:
        res = TestClient(app).get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        return res.json()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


def test_no_commitment_without_guarantee(db):
    c = _make_client(db)
    db.commit()
    assert _overview(db, c).get("commitment") is None


def test_at_risk_collapses_to_in_progress(db):
    c = _make_client(db)
    _guarantee(db, c)  # 45% elapsed, 0 gained → at_risk internally
    db.commit()
    commitment = _overview(db, c)["commitment"]
    assert commitment["state"] == "in_progress"
    # Whitelist: no internal fields leak.
    assert "last_state" not in commitment
    assert "admin_note" not in commitment
    assert commitment["baseline"] == 45
    assert commitment["target"] == 60
    assert commitment["current"] == 45.0


def test_deadline_passed_hidden_until_resolved(db):
    c = _make_client(db)
    _guarantee(db, c, start_days_ago=100, deadline_in=-1)
    db.commit()
    assert _overview(db, c).get("commitment") is None


def test_void_hidden(db):
    c = _make_client(db)
    _guarantee(db, c, status="void", resolved=True)
    db.commit()
    assert _overview(db, c).get("commitment") is None


def test_met_target_shows_achieved(db):
    c = _make_client(db)
    _guarantee(db, c, target=40)  # current 45 >= 40 → met → "achieved"
    db.commit()
    assert _overview(db, c)["commitment"]["state"] == "achieved"


def test_missed_shows_only_after_resolution(db):
    c = _make_client(db)
    _guarantee(db, c, status="missed", resolved=True, start_days_ago=120, deadline_in=-5)
    db.commit()
    commitment = _overview(db, c)["commitment"]
    assert commitment["state"] == "missed"
    assert "admin_note" not in commitment
