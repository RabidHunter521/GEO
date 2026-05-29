# backend/tests/test_competitor_intelligence.py
import uuid
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id):
    m = MagicMock()
    m.id = client_id
    m.archived_at = None
    return m


def _fake_competitor(comp_id, client_id, name="RivalCo"):
    m = MagicMock()
    m.id = comp_id
    m.client_id = client_id
    m.name = name
    m.website = f"https://{name.lower()}.com"
    return m


def _fake_scan(scan_id, client_id):
    m = MagicMock()
    m.id = scan_id
    m.client_id = client_id
    m.status = "completed"
    m.completed_at = datetime(2026, 5, 29, 12, 0)
    return m


def _fake_result(scan_id, competitor_id=None, category="brand", detected=True):
    m = MagicMock()
    m.scan_id = scan_id
    m.competitor_id = competitor_id
    m.category = category
    m.query_text = f"Test {category} query"
    m.brand_detected = detected
    return m


def _build_mock_db(client, scan, all_results, competitors):
    from app.models.scan import Scan as ScanModel
    from app.models.scan_query_result import ScanQueryResult as SQR
    from app.models.competitor import Competitor as CompModel

    scan_mock = MagicMock()
    scan_mock.filter.return_value.order_by.return_value.first.return_value = scan

    result_mock = MagicMock()
    result_mock.filter.return_value.all.return_value = all_results

    comp_mock = MagicMock()
    comp_mock.filter.return_value.all.return_value = competitors

    def query_side_effect(model):
        if model is ScanModel:
            return scan_mock
        if model is SQR:
            return result_mock
        if model is CompModel:
            return comp_mock
        return MagicMock()

    mock_db = MagicMock()
    mock_db.get.return_value = client
    mock_db.query.side_effect = query_side_effect
    return mock_db


def test_intelligence_no_scan_returns_null_citability():
    """No completed scan → client_ai_citability is null, competitors listed with 0%."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=None,
        all_results=[],
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    try:
        resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] is None
    assert data["last_scan_at"] is None
    assert len(data["competitors"]) == 1
    assert data["competitors"][0]["ai_citability"] == 0.0
    assert data["competitors"][0]["is_winning"] is False


def test_intelligence_competitor_winning():
    """Competitor detected in 3/4 queries (75%), client in 1/4 (25%) → is_winning True."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    client_results = [
        _fake_result(scan_id, None, "brand", True),
        _fake_result(scan_id, None, "comparison", False),
        _fake_result(scan_id, None, "recommendation", False),
        _fake_result(scan_id, None, "local", False),
    ]
    comp_results = [
        _fake_result(scan_id, comp_id, "brand", True),
        _fake_result(scan_id, comp_id, "comparison", True),
        _fake_result(scan_id, comp_id, "recommendation", True),
        _fake_result(scan_id, comp_id, "local", False),
    ]
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=_fake_scan(scan_id, client_id),
        all_results=client_results + comp_results,
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    try:
        resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] == 25.0
    comp = data["competitors"][0]
    assert comp["ai_citability"] == 75.0
    assert comp["is_winning"] is True
    assert len(comp["queries"]) == 4


def test_intelligence_competitor_losing():
    """Client at 100%, competitor at 50% → is_winning False."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    client_results = [
        _fake_result(scan_id, None, cat, True)
        for cat in ["brand", "comparison", "recommendation", "local"]
    ]
    comp_results = [
        _fake_result(scan_id, comp_id, "brand", True),
        _fake_result(scan_id, comp_id, "comparison", True),
        _fake_result(scan_id, comp_id, "recommendation", False),
        _fake_result(scan_id, comp_id, "local", False),
    ]
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=_fake_scan(scan_id, client_id),
        all_results=client_results + comp_results,
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    try:
        resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] == 100.0
    assert data["competitors"][0]["is_winning"] is False
    assert data["competitors"][0]["ai_citability"] == 50.0


def test_intelligence_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    try:
        resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/intelligence")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_intelligence_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/intelligence")
    assert resp.status_code == 401
