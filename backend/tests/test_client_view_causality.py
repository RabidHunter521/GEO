"""Client-view gate for the causal proof chart: the overview only carries
causal_trend once >=2 scans have control data, and the block is whitelisted
(dates + two frequency arrays — nothing internal)."""
import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def _make_client(db):
    from app.models.client import Client
    c = Client(
        id=uuid.uuid4(),
        name="Acme Dental",
        website="https://acmedental.com",
        industry="Dental",
        share_token=uuid.uuid4().hex,
        scan_cadence_days=30,
        is_prospect=False,
    )
    db.add(c)
    db.flush()
    return c


def _scan_with_rows(db, client_id, day, with_control):
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    s = Scan(
        id=uuid.uuid4(),
        client_id=client_id,
        status="completed",
        triggered_at=datetime(2026, 6, day),
        completed_at=datetime(2026, 6, day, 1),
    )
    db.add(s)
    db.flush()
    db.add(ScanQueryResult(
        id=uuid.uuid4(), scan_id=s.id, platform="gemini", competitor_id=None,
        category="recommendation", query_text="opt q", response_text="Acme is great",
        brand_detected=True, hallucination_flagged=False,
    ))
    if with_control:
        db.add(ScanQueryResult(
            id=uuid.uuid4(), scan_id=s.id, platform="gemini", competitor_id=None,
            category="recommendation", query_text="ctl q", response_text="others",
            brand_detected=False, hallucination_flagged=False, is_control=True,
        ))
    db.flush()
    return s


def _build_test_client(db):
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    return TestClient(app)


def _get_overview(db, client):
    _saved = dict(app.dependency_overrides)
    tc = _build_test_client(db)
    try:
        res = tc.get(f"/api/v1/view/{client.share_token}/overview")
        assert res.status_code == 200, res.text
        return res.json()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(_saved)


def test_causal_trend_absent_with_one_control_scan(db):
    client = _make_client(db)
    _scan_with_rows(db, client.id, 1, with_control=False)
    _scan_with_rows(db, client.id, 2, with_control=True)
    db.commit()
    body = _get_overview(db, client)
    assert body.get("causal_trend") is None


def test_causal_trend_present_with_two_control_scans(db):
    client = _make_client(db)
    _scan_with_rows(db, client.id, 1, with_control=True)
    _scan_with_rows(db, client.id, 2, with_control=True)
    db.commit()
    body = _get_overview(db, client)
    trend = body.get("causal_trend")
    assert trend is not None
    # Whitelist: exactly dates + the two frequency series.
    assert set(trend.keys()) == {"dates", "optimized", "left_alone"}
    assert len(trend["dates"]) == 2
    assert trend["optimized"] == [100.0, 100.0]
    assert trend["left_alone"] == [0.0, 0.0]
