"""Tests for scan_diff_service.compute_scan_diff.

Uses the in-memory SQLite `db` fixture from conftest.py.
"""
from datetime import datetime

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.scan_diff_service import compute_scan_diff


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_client(db) -> Client:
    c = Client(name="Acme", website="https://acme.com", industry="Technology")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_scan(db, client, completed_at: datetime) -> Scan:
    s = Scan(
        client_id=client.id,
        platform="multi",
        status="completed",
        completed_at=completed_at,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _make_result(db, scan, query_text: str, brand_detected: bool, platform="chatgpt",
                 category="recommendation") -> ScanQueryResult:
    r = ScanQueryResult(
        scan_id=scan.id,
        platform=platform,
        competitor_id=None,
        category=category,
        query_text=query_text,
        response_text="x",
        brand_detected=brand_detected,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── test 1: two scans — newly_seen and newly_unseen populated ─────────────────

def test_two_scans_diff_newly_seen_and_unseen(db):
    """
    Query A: was NOT seen by AI in prev scan → IS seen by AI in latest → appears in newly_seen.
    Query B: WAS seen by AI in prev scan → NOT seen by AI in latest → appears in newly_unseen.
    Query C: unchanged (seen both times) → does NOT appear in either list.
    has_comparison must be True.
    """
    client = _make_client(db)
    prev_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1, 12, 0, 0))
    latest_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 8, 12, 0, 0))

    # Query A: Not seen → Seen
    _make_result(db, prev_scan, "best restaurant in KL", brand_detected=False)
    _make_result(db, latest_scan, "best restaurant in KL", brand_detected=True)

    # Query B: Seen → Not seen
    _make_result(db, prev_scan, "top SEO agency Malaysia", brand_detected=True)
    _make_result(db, latest_scan, "top SEO agency Malaysia", brand_detected=False)

    # Query C: Seen both times (unchanged)
    _make_result(db, prev_scan, "AI visibility tool", brand_detected=True)
    _make_result(db, latest_scan, "AI visibility tool", brand_detected=True)

    result = compute_scan_diff(client.id, db)

    assert result.has_comparison is True
    assert result.latest_scan_id == latest_scan.id
    assert result.previous_scan_id == prev_scan.id

    newly_seen_queries = [q.query_text for q in result.newly_seen]
    assert "best restaurant in KL" in newly_seen_queries
    assert "top SEO agency Malaysia" not in newly_seen_queries
    assert "AI visibility tool" not in newly_seen_queries

    newly_unseen_queries = [q.query_text for q in result.newly_unseen]
    assert "top SEO agency Malaysia" in newly_unseen_queries
    assert "best restaurant in KL" not in newly_unseen_queries
    assert "AI visibility tool" not in newly_unseen_queries


def test_two_scans_diff_visibility_values(db):
    """latest_visibility and previous_visibility are computed from own results."""
    client = _make_client(db)
    prev_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1))
    latest_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 8))

    # prev: 1 of 2 seen = 50%
    _make_result(db, prev_scan, "query one", brand_detected=True)
    _make_result(db, prev_scan, "query two", brand_detected=False)

    # latest: 2 of 2 seen = 100%
    _make_result(db, latest_scan, "query one", brand_detected=True)
    _make_result(db, latest_scan, "query two", brand_detected=True)

    result = compute_scan_diff(client.id, db)

    assert result.has_comparison is True
    assert result.previous_visibility == 50.0
    assert result.latest_visibility == 100.0


# ── test 2: only one completed scan ──────────────────────────────────────────

def test_one_completed_scan_no_comparison(db):
    """Single completed scan: has_comparison=False, previous_scan_id=None, empty lists."""
    client = _make_client(db)
    scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1))
    _make_result(db, scan, "some query", brand_detected=True)

    result = compute_scan_diff(client.id, db)

    assert result.has_comparison is False
    assert result.previous_scan_id is None
    assert result.latest_scan_id == scan.id
    assert result.newly_seen == []
    assert result.newly_unseen == []
    assert result.latest_visibility == 100.0


def test_no_scans_returns_empty_response(db):
    """No completed scans returns a blank ScanDiffResponse."""
    client = _make_client(db)

    result = compute_scan_diff(client.id, db)

    assert result.has_comparison is False
    assert result.latest_scan_id is None
    assert result.previous_scan_id is None
    assert result.newly_seen == []
    assert result.newly_unseen == []


def test_pending_scan_is_excluded_from_diff(db):
    """A pending scan is not counted as a completed scan."""
    client = _make_client(db)
    completed = _make_scan(db, client, completed_at=datetime(2026, 6, 1))
    _make_result(db, completed, "query one", brand_detected=True)

    # Add a pending scan — should be ignored
    pending = Scan(client_id=client.id, platform="multi", status="pending")
    db.add(pending)
    db.commit()

    result = compute_scan_diff(client.id, db)

    # Still only one completed scan
    assert result.has_comparison is False
    assert result.latest_scan_id == completed.id


def test_competitor_results_excluded_from_diff(db):
    """Results with competitor_id set must not appear in newly_seen/newly_unseen."""
    from app.models.competitor import Competitor

    client = _make_client(db)
    prev_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1))
    latest_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 8))

    # Add a real competitor so FK constraint is satisfied
    comp = Competitor(client_id=client.id, name="Rival Co", website="https://rival.com")
    db.add(comp)
    db.commit()
    db.refresh(comp)

    # Competitor result — should be excluded
    comp_prev = ScanQueryResult(
        scan_id=prev_scan.id,
        platform="chatgpt",
        competitor_id=comp.id,
        category="recommendation",
        query_text="competitor query",
        response_text="x",
        brand_detected=False,
    )
    comp_latest = ScanQueryResult(
        scan_id=latest_scan.id,
        platform="chatgpt",
        competitor_id=comp.id,
        category="recommendation",
        query_text="competitor query",
        response_text="x",
        brand_detected=True,
    )
    db.add_all([comp_prev, comp_latest])
    db.commit()

    result = compute_scan_diff(client.id, db)

    # has_comparison True (two completed scans) but lists are empty — no own results
    assert result.has_comparison is True
    assert result.newly_seen == []
    assert result.newly_unseen == []


def test_query_only_in_latest_not_counted(db):
    """A query that appears only in the latest scan (new query) should not appear in diff."""
    client = _make_client(db)
    prev_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1))
    latest_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 8))

    # Common query
    _make_result(db, prev_scan, "common query", brand_detected=False)
    _make_result(db, latest_scan, "common query", brand_detected=False)

    # Brand new query only in latest (no prev counterpart)
    _make_result(db, latest_scan, "brand new query", brand_detected=True)

    result = compute_scan_diff(client.id, db)

    assert result.has_comparison is True
    newly_seen_queries = [q.query_text for q in result.newly_seen]
    assert "brand new query" not in newly_seen_queries
