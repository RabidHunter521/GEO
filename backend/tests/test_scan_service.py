# backend/tests/test_scan_service.py
import uuid
from unittest.mock import MagicMock, patch
from app.services.scan_service import run_scan


def make_scan(scan_id=None, client_id=None):
    scan = MagicMock()
    scan.id = scan_id or uuid.uuid4()
    scan.client_id = client_id or uuid.uuid4()
    scan.status = "pending"
    scan.platform = "multi"
    return scan


def make_client(name="ACME Corp", enabled_platforms=None):
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = name
    client.industry = "consulting"
    client.city = "Kuala Lumpur"
    client.state = "WP"
    client.brand_authority_score = 50
    client.content_quality_score = 50
    client.technical_foundations_verified = False
    client.structured_data_verified = False
    client.enabled_platforms = enabled_platforms or ["gemini"]
    return client


def make_result(platform="gemini", brand_detected=True, competitor_id=None):
    return MagicMock(
        platform=platform, brand_detected=brand_detected, competitor_id=competitor_id
    )


def setup_db(scan, client, stored_results):
    """Mock session: first() → scan then client; all() → competitors then results."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [],              # competitors query
        stored_results,  # scan_query_results query (for scoring)
    ]
    return mock_db


def patch_platform_client(query_fn):
    mock_client = MagicMock()
    mock_client.query.side_effect = query_fn
    return patch(
        "app.services.scan_service.get_platform_client", return_value=mock_client
    ), mock_client


def test_run_scan_sets_status_to_completed():
    scan = make_scan()
    client = make_client()
    mock_db = setup_db(scan, client, [make_result()])

    patcher, _ = patch_platform_client(lambda q: "ACME Corp is great.")
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    assert scan.status == "completed"


def test_run_scan_creates_geo_score_with_platform_breakdown():
    scan = make_scan()
    client = make_client(enabled_platforms=["gemini", "claude"])
    stored = [
        make_result("gemini", brand_detected=True),
        make_result("gemini", brand_detected=False),
        make_result("claude", brand_detected=True),
        make_result("claude", brand_detected=True),
    ]
    mock_db = setup_db(scan, client, stored)

    added_objects = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    patcher, _ = patch_platform_client(lambda q: "ACME Corp mentioned.")
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    from app.models.geo_score import GeoScore
    geo_scores = [o for o in added_objects if isinstance(o, GeoScore)]
    assert len(geo_scores) == 1
    breakdown = geo_scores[0].platform_breakdown
    assert breakdown["gemini"] == {"visibility": 50.0, "queries": 2, "detected": 1, "status": "ok"}
    assert breakdown["claude"] == {"visibility": 100.0, "queries": 2, "detected": 2, "status": "ok"}
    # citability = equal-weighted mean of per-platform visibility
    assert geo_scores[0].ai_citability == 75.0


def test_run_scan_queries_every_enabled_platform():
    scan = make_scan()
    client = make_client(enabled_platforms=["chatgpt", "perplexity", "gemini", "claude"])
    mock_db = setup_db(scan, client, [make_result()])

    requested_platforms = []

    def fake_get_client(platform):
        requested_platforms.append(platform)
        mock_client = MagicMock()
        mock_client.query.return_value = "ACME Corp is great."
        return mock_client

    with patch(
        "app.services.scan_service.get_platform_client", side_effect=fake_get_client
    ), patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    assert requested_platforms == ["chatgpt", "perplexity", "gemini", "claude"]
    assert scan.status == "completed"


def test_run_scan_tags_results_with_platform():
    scan = make_scan()
    client = make_client(enabled_platforms=["gemini", "claude"])
    mock_db = setup_db(scan, client, [make_result()])

    persisted = []
    mock_db.add_all.side_effect = lambda objs: persisted.extend(objs)

    patcher, _ = patch_platform_client(lambda q: "ACME Corp is listed.")
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    platforms = {r.platform for r in persisted}
    assert platforms == {"gemini", "claude"}
    # 15 client queries per platform (5 per category; comparison is skipped with
    # no competitors) × 2 platforms = 30
    assert len(persisted) == 30
    per_platform = {p: sum(1 for r in persisted if r.platform == p) for p in platforms}
    assert per_platform == {"gemini": 15, "claude": 15}


def test_run_scan_populates_recommendation_position_for_ranked_categories():
    scan = make_scan()
    client = make_client()
    mock_db = setup_db(scan, client, [make_result()])

    persisted = []
    mock_db.add_all.side_effect = lambda objs: persisted.extend(objs)

    patcher, _ = patch_platform_client(lambda q: "ACME Corp is listed.")
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=2
    ) as mock_extract:
        run_scan(scan.id, mock_db)

    ranked = [r for r in persisted if r.category in ("recommendation", "local")]
    other = [r for r in persisted if r.category not in ("recommendation", "local")]

    # extraction only runs for ranked categories where the brand was detected
    assert mock_extract.call_count == len(ranked)
    assert all(r.recommendation_position == 2 for r in ranked)
    assert all(r.recommendation_position is None for r in other)


def test_run_scan_single_platform_failure_does_not_fail_scan():
    scan = make_scan()
    client = make_client(enabled_platforms=["gemini", "claude"])
    # Only gemini results end up stored — claude failed
    mock_db = setup_db(scan, client, [make_result("gemini", brand_detected=True)])

    added_objects = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    def fake_get_client(platform):
        mock_client = MagicMock()
        if platform == "claude":
            mock_client.query.side_effect = Exception("Claude unavailable")
        else:
            mock_client.query.return_value = "ACME Corp is great."
        return mock_client

    with patch(
        "app.services.scan_service.get_platform_client", side_effect=fake_get_client
    ), patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    assert scan.status == "completed"

    from app.models.geo_score import GeoScore
    from app.models.activity_log import ActivityLog
    geo_scores = [o for o in added_objects if isinstance(o, GeoScore)]
    assert len(geo_scores) == 1
    assert geo_scores[0].platform_breakdown["claude"]["status"] == "unavailable"
    # unavailable platform is excluded from the citability average
    assert geo_scores[0].ai_citability == 100.0

    unavailable_logs = [
        o for o in added_objects
        if isinstance(o, ActivityLog) and o.event_type == "scan_platform_unavailable"
    ]
    assert len(unavailable_logs) == 1
    assert "Claude" in unavailable_logs[0].note


def test_run_scan_sets_failed_when_all_platforms_fail():
    scan = make_scan()
    client = make_client(enabled_platforms=["gemini", "claude"])
    mock_db = setup_db(scan, client, [])  # nothing stored — every platform failed

    patcher, _ = patch_platform_client(MagicMock(side_effect=Exception("API down")))
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ):
        run_scan(scan.id, mock_db)

    assert scan.status == "failed"


# ── has_active_scan (scan-in-progress guard) ─────────────────────────────────

def _guard_client(db):
    from app.models.client import Client
    c = Client(name="Acme", website="https://acme.com", industry="Tech")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _guard_scan(db, client, status, minutes_ago):
    from datetime import datetime, timedelta, timezone
    from app.models.scan import Scan
    s = Scan(
        client_id=client.id,
        platform="multi",
        status=status,
        triggered_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes_ago),
    )
    db.add(s)
    db.commit()
    return s


def test_has_active_scan_true_for_recent_pending(db):
    from app.services.scan_service import has_active_scan
    c = _guard_client(db)
    _guard_scan(db, c, "pending", minutes_ago=1)
    assert has_active_scan(c.id, db) is True


def test_has_active_scan_true_for_recent_running(db):
    from app.services.scan_service import has_active_scan
    c = _guard_client(db)
    _guard_scan(db, c, "running", minutes_ago=5)
    assert has_active_scan(c.id, db) is True


def test_has_active_scan_false_for_completed(db):
    from app.services.scan_service import has_active_scan
    c = _guard_client(db)
    _guard_scan(db, c, "completed", minutes_ago=1)
    assert has_active_scan(c.id, db) is False


def test_has_active_scan_false_for_stale_running(db):
    from app.services.scan_service import has_active_scan
    c = _guard_client(db)
    # Crashed worker scenario: running scan older than the stale window
    _guard_scan(db, c, "running", minutes_ago=20)
    assert has_active_scan(c.id, db) is False


def test_has_active_scan_scoped_to_client(db):
    from app.services.scan_service import has_active_scan
    a = _guard_client(db)
    b = _guard_client(db)
    _guard_scan(db, a, "running", minutes_ago=1)
    assert has_active_scan(b.id, db) is False
