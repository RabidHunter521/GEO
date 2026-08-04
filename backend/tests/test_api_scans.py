import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.schemas.scan import ScanDiffQuery, ScanDiffResponse
from app.services.platform_clients.base import PlatformResult


def test_health_endpoint():
    from app.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_scan_returns_202():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_scan = MagicMock()
    mock_scan.id = uuid.uuid4()
    mock_scan.client_id = uuid.uuid4()
    mock_scan.platform = "gemini"
    mock_scan.status = "pending"
    from datetime import datetime
    mock_scan.triggered_at = datetime(2026, 1, 1, 0, 0, 0)
    mock_scan.completed_at = None

    mock_client = MagicMock()
    mock_client.archived_at = None

    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.get.return_value = mock_client
    # No active scan — the in-progress guard queries Scan and checks first()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def fake_refresh(scan_obj):
        scan_obj.id = mock_scan.id
        scan_obj.client_id = mock_scan.client_id
        scan_obj.platform = mock_scan.platform
        scan_obj.status = mock_scan.status
        scan_obj.triggered_at = mock_scan.triggered_at
        scan_obj.completed_at = mock_scan.completed_at

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    def fake_get_db():
        yield mock_db

    from app.services.budget_service import BudgetStatus
    from decimal import Decimal
    ok_budget = BudgetStatus(
        ok=True, reason=None, client_spend=Decimal("0"), global_spend=Decimal("0"),
        client_cap=20.0, global_cap=50.0,
    )

    with patch("workers.tasks.scan_tasks.execute_scan") as mock_task, patch(
        "app.services.budget_service.check_budget", return_value=ok_budget
    ):
        mock_task.delay = MagicMock()
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        client = TestClient(app)
        response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
        app.dependency_overrides.clear()

    assert response.status_code == 202


def test_trigger_scan_conflict_when_scan_active():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_client = MagicMock()
    mock_client.archived_at = None

    mock_db = MagicMock()
    mock_db.get.return_value = mock_client

    def fake_get_db():
        yield mock_db

    with patch("app.services.scan_service.has_active_scan", return_value=True):
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        client = TestClient(app)
        response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_trigger_scan_blocked_when_over_budget():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    from app.services.budget_service import BudgetStatus
    from decimal import Decimal

    mock_client = MagicMock()
    mock_client.archived_at = None

    mock_db = MagicMock()
    mock_db.get.return_value = mock_client

    blocked = BudgetStatus(
        ok=False,
        reason="Global daily spend cap reached ($60.00 of $50.00).",
        client_spend=Decimal("1"),
        global_spend=Decimal("60"),
        client_cap=20.0,
        global_cap=50.0,
    )

    def fake_get_db():
        yield mock_db

    with patch("app.services.scan_service.has_active_scan", return_value=False), patch(
        "app.services.budget_service.check_budget", return_value=blocked
    ), patch("app.services.alert_service.notify_budget_exceeded") as mock_alert, patch(
        "workers.tasks.scan_tasks.execute_scan"
    ) as mock_task:
        mock_task.delay = MagicMock()
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        client = TestClient(app)
        response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
        app.dependency_overrides.clear()

    assert response.status_code == 402
    assert "cap" in response.json()["detail"].lower()
    mock_alert.assert_called_once()
    # Blocked: the scan task must never be dispatched.
    mock_task.delay.assert_not_called()


def test_trigger_scan_unknown_client_returns_404():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_db = MagicMock()
    mock_db.get.return_value = None

    def fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[require_api_key] = lambda: None
    client = TestClient(app)
    response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_trigger_scan_requires_auth():
    from app.main import app
    client = TestClient(app)
    response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_get_scan_not_found():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[require_api_key] = lambda: None
    client = TestClient(app)
    response = client.get(f"/api/v1/scans/{uuid.uuid4()}")
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_get_scan_diff_returns_200_with_comparison():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    client_id = uuid.uuid4()
    mock_diff = ScanDiffResponse(
        has_comparison=True,
        newly_seen=[
            ScanDiffQuery(platform="chatgpt", category="recommendation", query_text="q1")
        ],
        newly_unseen=[],
    )

    def fake_get_db():
        yield MagicMock()

    with patch("app.api.v1.scans.compute_scan_diff", return_value=mock_diff):
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        http_client = TestClient(app)
        response = http_client.get(f"/api/v1/scans/client/{client_id}/diff")
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["has_comparison"] is True
    assert len(body["newly_seen"]) == 1
    assert body["newly_seen"][0]["query_text"] == "q1"
    assert body["newly_seen"][0]["platform"] == "chatgpt"
    assert body["newly_unseen"] == []


def test_get_scan_diff_no_comparison():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    client_id = uuid.uuid4()
    mock_diff = ScanDiffResponse(has_comparison=False)

    def fake_get_db():
        yield MagicMock()

    with patch("app.api.v1.scans.compute_scan_diff", return_value=mock_diff):
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        http_client = TestClient(app)
        response = http_client.get(f"/api/v1/scans/client/{client_id}/diff")
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["has_comparison"] is False
    assert body["newly_seen"] == []
    assert body["newly_unseen"] == []


def test_get_scan_diff_requires_auth():
    from app.main import app

    http_client = TestClient(app)
    response = http_client.get(f"/api/v1/scans/client/{uuid.uuid4()}/diff")
    assert response.status_code == 401


# --- snippet endpoint tests ---

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_get_result_snippet_returns_png():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    scan_id = uuid.uuid4()
    result_id = uuid.uuid4()
    client_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scan_id = scan_id
    mock_result.competitor_id = None
    mock_result.response_text = "Acme Dental is the best clinic in KL."
    mock_result.platform = "chatgpt"

    mock_scan = MagicMock()
    mock_scan.client_id = client_id

    mock_client = MagicMock()
    mock_client.id = client_id
    mock_client.name = "Acme Dental"

    mock_db = MagicMock()
    mock_db.get.side_effect = [mock_result, mock_scan, mock_client]
    mock_db.query.return_value.filter.return_value.all.return_value = []

    def fake_get_db():
        yield mock_db

    with patch("app.api.v1.scans.snippet_service.build_excerpt", return_value="Acme Dental is the best clinic in KL."), \
         patch("app.api.v1.scans.snippet_service.render_snippet_png", return_value=PNG_MAGIC + b"\x00" * 2000):
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        http_client = TestClient(app)
        response = http_client.get(f"/api/v1/scans/{scan_id}/results/{result_id}/snippet.png")
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content[:8] == PNG_MAGIC


def test_get_result_snippet_404_when_result_missing():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    mock_db = MagicMock()
    mock_db.get.return_value = None

    def fake_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[require_api_key] = lambda: None
    http_client = TestClient(app)
    response = http_client.get(f"/api/v1/scans/{uuid.uuid4()}/results/{uuid.uuid4()}/snippet.png")
    app.dependency_overrides.clear()

    assert response.status_code == 404


def test_get_result_snippet_401_without_auth():
    from app.main import app

    http_client = TestClient(app)
    response = http_client.get(f"/api/v1/scans/{uuid.uuid4()}/results/{uuid.uuid4()}/snippet.png")
    assert response.status_code == 401


# ── tracked-query repeat sampling integration (Phase 5 Task 3) ──────────────
# These run run_scan() directly against a real (SQLite) `db` session rather
# than mocking the session, because the sampling wiring depends on real
# TrackedQuery/ScanQueryResult rows and their DB-enforced link — a MagicMock
# session cannot prove the join actually happens (see the Phase 4 lesson in
# .superpowers/sdd/progress.md: "each unit passing does not prove the seam
# exists, and the seam IS the feature").

def _as_result(text, model="test-model"):
    return PlatformResult(text=text, model=model, input_tokens=1, output_tokens=1)


def _sampling_client(db, **overrides):
    from app.models.client import Client
    defaults = dict(
        name="Acme Dental", website="https://acme.com", industry="dental",
        enabled_platforms=["gemini"],
    )
    defaults.update(overrides)
    client = Client(**defaults)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def _sampling_scan(db, client):
    from app.models.scan import Scan
    scan = Scan(client_id=client.id, platform="multi", status="pending")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _tracked_query(db, client, *, text, intent="recommendation", risk_level="standard", is_active=True):
    from app.models.tracked_query import TrackedQuery
    tq = TrackedQuery(
        client_id=client.id,
        text=text,
        normalized_text=text.lower(),
        source="manual",
        intent=intent,
        risk_level=risk_level,
        is_active=is_active,
    )
    db.add(tq)
    db.commit()
    db.refresh(tq)
    return tq


def test_run_scan_links_high_risk_tracked_query_samples_with_no_duplicates(db):
    from app.services.scan_service import run_scan
    from app.models.scan_query_result import ScanQueryResult

    client = _sampling_client(db)
    scan = _sampling_scan(db, client)
    tq = _tracked_query(db, client, text="Is Acme Dental a scam?", risk_level="critical")

    mock_platform_client = MagicMock()
    mock_platform_client.query.side_effect = lambda q: _as_result(f"Answer to: {q}")

    with patch("app.services.scan_service.get_platform_client", return_value=mock_platform_client), \
         patch("app.services.scan_service.time.sleep"), \
         patch("app.services.scan_service.extract_position", return_value=None):
        run_scan(scan.id, db)

    db.refresh(scan)
    assert scan.status == "completed"

    rows = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.tracked_query_id == tq.id)
        .order_by(ScanQueryResult.sample_index)
        .all()
    )
    # High-risk query defaults to 3 repetitions (query_sampling_service.HIGH_PRIORITY_REPETITIONS).
    assert [r.sample_index for r in rows] == [1, 2, 3]
    assert len({r.sample_index for r in rows}) == 3  # no duplicate sample_index
    assert all(r.query_text == tq.text for r in rows)  # original text retained verbatim
    assert all(r.model_name == "test-model" for r in rows)  # model logged, not left "unknown"
    assert all(r.platform == "gemini" for r in rows)


def test_run_scan_never_samples_an_inactive_tracked_query(db):
    from app.services.scan_service import run_scan
    from app.models.scan_query_result import ScanQueryResult

    client = _sampling_client(db)
    scan = _sampling_scan(db, client)
    archived = _tracked_query(
        db, client, text="Archived question", risk_level="critical", is_active=False,
    )

    mock_platform_client = MagicMock()
    mock_platform_client.query.side_effect = lambda q: _as_result(f"Answer to: {q}")

    with patch("app.services.scan_service.get_platform_client", return_value=mock_platform_client), \
         patch("app.services.scan_service.time.sleep"), \
         patch("app.services.scan_service.extract_position", return_value=None):
        run_scan(scan.id, db)

    db.refresh(scan)
    assert scan.status == "completed"

    rows = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.tracked_query_id == archived.id)
        .all()
    )
    assert rows == []


def test_run_scan_partial_sample_failure_keeps_completed_samples_and_scan_recoverable(db):
    """A provider hiccup on one repetition of a tracked query must not lose
    the samples that already succeeded, and must not fail the scan — the
    Task 3 brief's 'partial provider failure records only completed samples
    and leaves the scan recoverable.'"""
    from app.services.scan_service import run_scan
    from app.models.scan_query_result import ScanQueryResult

    client = _sampling_client(db)
    scan = _sampling_scan(db, client)
    tq = _tracked_query(db, client, text="Is Acme Dental reputable?", risk_level="critical")

    call_counts: dict[str, int] = {}

    def fake_query(q):
        if q == tq.text:
            call_counts[q] = call_counts.get(q, 0) + 1
            if call_counts[q] == 2:
                raise Exception("provider hiccup")
        return _as_result(f"Answer to: {q}")

    mock_platform_client = MagicMock()
    mock_platform_client.query.side_effect = fake_query

    with patch("app.services.scan_service.get_platform_client", return_value=mock_platform_client), \
         patch("app.services.scan_service.time.sleep"), \
         patch("app.services.scan_service.extract_position", return_value=None):
        run_scan(scan.id, db)

    db.refresh(scan)
    # The scan as a whole still completes — one failed repetition does not
    # sink the platform or the scan.
    assert scan.status == "completed"

    rows = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.tracked_query_id == tq.id)
        .order_by(ScanQueryResult.sample_index)
        .all()
    )
    # Repetition 2 of 3 failed and was skipped; 1 and 3 are still recorded —
    # no gap-filling, no duplicate, no silently dropped scan.
    assert [r.sample_index for r in rows] == [1, 3]


def test_run_scan_repeat_samples_respect_the_remaining_budget(db, monkeypatch):
    """When the budget is exhausted, run_scan must not add tracked-query
    repeat-sample spend on top of it — the sampling plan is capped to zero
    add-on queries rather than bypassing the cap."""
    from app.services.scan_service import run_scan
    from app.services import budget_service
    from app.models.scan_query_result import ScanQueryResult

    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 0.001)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 1000.0)

    client = _sampling_client(db)
    scan = _sampling_scan(db, client)
    tq = _tracked_query(db, client, text="Is Acme Dental reputable?", risk_level="critical")

    mock_platform_client = MagicMock()
    mock_platform_client.query.side_effect = lambda q: _as_result(f"Answer to: {q}")

    with patch("app.services.scan_service.get_platform_client", return_value=mock_platform_client), \
         patch("app.services.scan_service.time.sleep"), \
         patch("app.services.scan_service.extract_position", return_value=None):
        run_scan(scan.id, db)

    db.refresh(scan)
    assert scan.status == "completed"

    rows = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.tracked_query_id == tq.id)
        .all()
    )
    # $0.001 of headroom cannot afford even one $0.01 sample, so the
    # tracked-query add-on is capped to nothing this scan. The scan's
    # ordinary (non-tracked) queries are unaffected — check_budget's
    # pre-trigger block is what would have stopped those, not this cap.
    assert rows == []


def test_get_result_snippet_404_when_no_excerpt():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key

    scan_id = uuid.uuid4()
    result_id = uuid.uuid4()
    client_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scan_id = scan_id
    mock_result.competitor_id = None
    mock_result.response_text = "No mention of the brand here."
    mock_result.platform = "chatgpt"

    mock_scan = MagicMock()
    mock_scan.client_id = client_id

    mock_client = MagicMock()
    mock_client.id = client_id
    mock_client.name = "Acme Dental"

    mock_db = MagicMock()
    mock_db.get.side_effect = [mock_result, mock_scan, mock_client]
    mock_db.query.return_value.filter.return_value.all.return_value = []

    def fake_get_db():
        yield mock_db

    with patch("app.api.v1.scans.snippet_service.build_excerpt", return_value=None):
        app.dependency_overrides[get_db] = fake_get_db
        app.dependency_overrides[require_api_key] = lambda: None
        http_client = TestClient(app)
        response = http_client.get(f"/api/v1/scans/{scan_id}/results/{result_id}/snippet.png")
        app.dependency_overrides.clear()

    assert response.status_code == 404
