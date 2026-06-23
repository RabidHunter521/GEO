"""Tests for gap_matrix_service.compute_gap_matrix.

Uses the in-memory SQLite `db` fixture from conftest.py.
"""
from datetime import datetime

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.gap_matrix_service import compute_gap_matrix


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_client(db, name="Acme", is_prospect=False, archived_at=None) -> Client:
    c = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.com",
        industry="Technology",
        is_prospect=is_prospect,
        archived_at=archived_at,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_competitor(db, client, name="Rival Co") -> Competitor:
    comp = Competitor(client_id=client.id, name=name)
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


def _make_scan(db, client, completed_at=None) -> Scan:
    s = Scan(
        client_id=client.id,
        platform="multi",
        status="completed",
        completed_at=completed_at or datetime(2026, 6, 1, 12, 0, 0),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _make_result(db, scan, category, brand_detected, competitor_id=None) -> ScanQueryResult:
    r = ScanQueryResult(
        scan_id=scan.id,
        platform="chatgpt",
        competitor_id=competitor_id,
        category=category,
        query_text=f"{category} query",
        response_text="x",
        brand_detected=brand_detected,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── test 1: competitor winning ────────────────────────────────────────────────

def test_competitors_winning_when_client_not_seen_but_competitor_is(db):
    """
    Client has brand_detected=False in recommendation; competitor has brand_detected=True.
    Expect competitors_winning=True and top_competitor_name set.
    """
    client = _make_client(db, "Acme")
    comp = _make_competitor(db, client, "Rival Co")
    scan = _make_scan(db, client)

    # Client own result: not seen
    _make_result(db, scan, "recommendation", brand_detected=False, competitor_id=None)
    # Competitor result: seen
    _make_result(db, scan, "recommendation", brand_detected=True, competitor_id=comp.id)

    matrix = compute_gap_matrix(db)

    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    assert row.client_name == "Acme"

    rec_cell = next(c for c in row.cells if c.category == "recommendation")
    assert rec_cell.competitors_winning is True
    assert rec_cell.top_competitor_name == "Rival Co"
    assert rec_cell.client_visibility == 0.0
    assert rec_cell.top_competitor_visibility == 100.0


# ── test 2: client leading ────────────────────────────────────────────────────

def test_competitors_not_winning_when_client_leads(db):
    """
    Client has brand_detected=True; competitor has brand_detected=False.
    Expect competitors_winning=False.
    """
    client = _make_client(db, "Leader Co")
    comp = _make_competitor(db, client, "Laggard Inc")
    scan = _make_scan(db, client)

    # Client own result: seen
    _make_result(db, scan, "recommendation", brand_detected=True, competitor_id=None)
    # Competitor result: not seen
    _make_result(db, scan, "recommendation", brand_detected=False, competitor_id=comp.id)

    matrix = compute_gap_matrix(db)

    assert len(matrix.rows) == 1
    rec_cell = next(c for c in matrix.rows[0].cells if c.category == "recommendation")
    assert rec_cell.competitors_winning is False
    assert rec_cell.client_visibility == 100.0
    assert rec_cell.top_competitor_visibility == 0.0


# ── test 3: prospects excluded ────────────────────────────────────────────────

def test_prospects_excluded_from_matrix(db):
    """Clients with is_prospect=True must not appear in rows."""
    _make_client(db, "Real Client", is_prospect=False)
    _make_client(db, "Prospect Lead", is_prospect=True)

    matrix = compute_gap_matrix(db)

    names = [r.client_name for r in matrix.rows]
    assert "Real Client" in names
    assert "Prospect Lead" not in names


# ── test 4: archived clients excluded ────────────────────────────────────────

def test_archived_clients_excluded_from_matrix(db):
    """Clients with archived_at set must not appear in rows."""
    _make_client(db, "Active Co", archived_at=None)
    _make_client(db, "Churned Co", archived_at=datetime(2026, 1, 1))

    matrix = compute_gap_matrix(db)

    names = [r.client_name for r in matrix.rows]
    assert "Active Co" in names
    assert "Churned Co" not in names


# ── test 5: categories are recommendation and local ──────────────────────────

def test_categories_are_recommendation_and_local(db):
    """GapMatrixResponse.categories must equal ['recommendation', 'local']."""
    matrix = compute_gap_matrix(db)
    assert matrix.categories == ["recommendation", "local"]


# ── test 6: client with no scan has empty cells ───────────────────────────────

def test_client_with_no_completed_scan_has_empty_cells(db):
    """A real client with no completed scan gets a row with cells=[]."""
    _make_client(db, "Unscan Co")

    matrix = compute_gap_matrix(db)

    assert len(matrix.rows) == 1
    assert matrix.rows[0].cells == []


# ── test 7: no competitors → client_vis computed, no winner ──────────────────

def test_no_competitors_means_no_winner(db):
    """When there are no competitors, competitors_winning must always be False."""
    client = _make_client(db, "Solo Brand")
    scan = _make_scan(db, client)
    _make_result(db, scan, "recommendation", brand_detected=False, competitor_id=None)

    matrix = compute_gap_matrix(db)

    rec_cell = next(c for c in matrix.rows[0].cells if c.category == "recommendation")
    assert rec_cell.competitors_winning is False
    assert rec_cell.top_competitor_name is None
    assert rec_cell.client_visibility == 0.0


# ── test 8: both seen equally → not winning ──────────────────────────────────

def test_equal_visibility_is_not_winning(db):
    """When competitor visibility == client visibility, competitors_winning must be False."""
    client = _make_client(db, "Tie Co")
    comp = _make_competitor(db, client, "Rival")
    scan = _make_scan(db, client)

    _make_result(db, scan, "local", brand_detected=True, competitor_id=None)
    _make_result(db, scan, "local", brand_detected=True, competitor_id=comp.id)

    matrix = compute_gap_matrix(db)

    local_cell = next(c for c in matrix.rows[0].cells if c.category == "local")
    assert local_cell.competitors_winning is False
    assert local_cell.client_visibility == 100.0
    assert local_cell.top_competitor_visibility == 100.0


# ── test 8b: uses the latest completed scan when a client has several ─────────

def test_uses_latest_completed_scan(db):
    """With multiple completed scans, the matrix reflects the most recent one."""
    client = _make_client(db, "Multi Scan Co")

    old_scan = _make_scan(db, client, completed_at=datetime(2026, 5, 1, 9, 0, 0))
    _make_result(db, old_scan, "recommendation", brand_detected=True, competitor_id=None)

    new_scan = _make_scan(db, client, completed_at=datetime(2026, 6, 1, 9, 0, 0))
    _make_result(db, new_scan, "recommendation", brand_detected=False, competitor_id=None)

    matrix = compute_gap_matrix(db)

    rec_cell = next(c for c in matrix.rows[0].cells if c.category == "recommendation")
    # Latest scan had brand_detected=False → 0%, not the old scan's 100%.
    assert rec_cell.client_visibility == 0.0


def test_results_are_not_cross_contaminated_between_clients(db):
    """Each client's cells reflect only its own latest scan's results."""
    a = _make_client(db, "Alpha")
    b = _make_client(db, "Bravo")
    scan_a = _make_scan(db, a)
    scan_b = _make_scan(db, b)
    _make_result(db, scan_a, "recommendation", brand_detected=True, competitor_id=None)
    _make_result(db, scan_b, "recommendation", brand_detected=False, competitor_id=None)

    matrix = compute_gap_matrix(db)
    by_name = {r.client_name: r for r in matrix.rows}

    a_cell = next(c for c in by_name["Alpha"].cells if c.category == "recommendation")
    b_cell = next(c for c in by_name["Bravo"].cells if c.category == "recommendation")
    assert a_cell.client_visibility == 100.0
    assert b_cell.client_visibility == 0.0


# ── test 9: hallucination-flagged rows are excluded ──────────────────────────

def test_hallucination_flagged_results_excluded(db):
    """A flagged 'seen' row must not inflate visibility — consistent with win_loss_service."""
    client = _make_client(db, "Flagged Co")
    scan = _make_scan(db, client)

    # Flagged + detected → must be ignored.
    db.add(ScanQueryResult(
        scan_id=scan.id, platform="chatgpt", competitor_id=None,
        category="recommendation", query_text="rec q1", response_text="x",
        brand_detected=True, hallucination_flagged=True,
    ))
    # Unflagged + not detected → counts.
    _make_result(db, scan, "recommendation", brand_detected=False, competitor_id=None)

    matrix = compute_gap_matrix(db)

    rec_cell = next(c for c in matrix.rows[0].cells if c.category == "recommendation")
    # Only the unflagged (not-detected) row counts → 0%, not 50%.
    assert rec_cell.client_visibility == 0.0
