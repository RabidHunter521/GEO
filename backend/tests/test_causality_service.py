from datetime import datetime, timedelta

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.causality_service import compute_causal_trend


def _scan(db, client, days_ago, opt_seen, opt_total, ctl_seen, ctl_total):
    s = Scan(client_id=client.id, status="completed")
    s.completed_at = datetime.utcnow() - timedelta(days=days_ago)
    db.add(s)
    db.commit()
    rows = [
        ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                        query_text=f"opt{i}", brand_detected=i < opt_seen)
        for i in range(opt_total)
    ] + [
        ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                        query_text=f"ctl{i}", brand_detected=i < ctl_seen, is_control=True)
        for i in range(ctl_total)
    ]
    db.add_all(rows)
    db.commit()
    return s


def test_two_series_split(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    _scan(db, c, 30, opt_seen=2, opt_total=4, ctl_seen=1, ctl_total=2)
    _scan(db, c, 1, opt_seen=3, opt_total=4, ctl_seen=1, ctl_total=2)
    trend = compute_causal_trend(c.id, db)
    assert len(trend.points) == 2
    assert trend.points[0].optimized_frequency == 50.0
    assert trend.points[1].optimized_frequency == 75.0
    assert trend.points[0].control_frequency == 50.0
    assert trend.points[1].control_frequency == 50.0


def test_no_control_rows_yields_none_frequency(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    _scan(db, c, 1, opt_seen=1, opt_total=2, ctl_seen=0, ctl_total=0)
    trend = compute_causal_trend(c.id, db)
    assert trend.points[0].control_frequency is None
    assert trend.points[0].optimized_frequency == 50.0
