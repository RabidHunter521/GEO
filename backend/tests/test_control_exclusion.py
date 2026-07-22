"""THE invariant: a control row changes nothing outside the causal chart."""
from datetime import datetime

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.scoring_service import compute_ai_citability, compute_platform_breakdown
from app.services.win_loss_service import compute_win_loss


def _seed(db, with_control):
    c = Client(name="Clinic A", website="https://a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed")
    s.completed_at = datetime.utcnow()
    db.add(s)
    db.commit()
    rows = [ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                            query_text="best dental clinic in KL", response_text="Clinic A is great",
                            brand_detected=True)]
    if with_control:
        rows.append(ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                                    query_text="best physio in Penang", response_text="others",
                                    brand_detected=False, is_control=True))
    db.add_all(rows)
    db.commit()
    return c, s, rows


def test_citability_identical_with_and_without_control(db):
    c, s, rows = _seed(db, with_control=True)
    bd = compute_platform_breakdown(rows)
    assert bd["chatgpt"]["queries"] == 1  # control excluded
    assert compute_ai_citability(rows, bd) == 100.0
    assert compute_ai_citability([r for r in rows if not r.is_control]) == 100.0


def test_legacy_citability_path_excludes_controls(db):
    c, s, rows = _seed(db, with_control=True)
    # Legacy path (no breakdown): flat ratio over client rows must skip controls.
    assert compute_ai_citability(rows) == 100.0


def test_win_loss_ignores_control_rows(db):
    c, s, rows = _seed(db, with_control=True)
    wl = compute_win_loss(c.id, db)
    assert all(e.query_text != "best physio in Penang" for e in wl.entries)
