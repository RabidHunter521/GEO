# backend/tests/test_competitor_trends.py
from datetime import datetime, timedelta

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.competitor_intelligence_service import compute_competitor_trends


def _seed_client(db):
    client = Client(name="ACME Corp", website="https://acme.example", industry="Technology")
    db.add(client)
    db.commit()
    return client


def _seed_scan_with_results(db, client, completed_at, client_detected, comp_detected=None, competitor=None, total=4):
    scan = Scan(client_id=client.id, status="completed", completed_at=completed_at)
    db.add(scan)
    db.commit()
    for i in range(total):
        db.add(ScanQueryResult(
            scan_id=scan.id, platform="gemini", category="brand",
            query_text=f"q{i}", brand_detected=i < client_detected,
        ))
    if competitor is not None and comp_detected is not None:
        for i in range(total):
            db.add(ScanQueryResult(
                scan_id=scan.id, platform="gemini", category="brand", competitor_id=competitor.id,
                query_text=f"cq{i}", brand_detected=i < comp_detected,
            ))
    db.commit()
    return scan


def test_trends_ordered_oldest_to_newest_with_visibility(db):
    client = _seed_client(db)
    comp = Competitor(client_id=client.id, name="RivalCo")
    db.add(comp)
    db.commit()

    _seed_scan_with_results(db, client, datetime(2026, 5, 1), client_detected=1, comp_detected=4, competitor=comp)
    _seed_scan_with_results(db, client, datetime(2026, 6, 1), client_detected=3, comp_detected=2, competitor=comp)

    trends = compute_competitor_trends(client.id, db)

    assert [s.completed_at for s in trends.scans] == [datetime(2026, 5, 1), datetime(2026, 6, 1)]
    assert trends.client.name == "ACME Corp"
    assert trends.client.points == [25.0, 75.0]
    assert trends.competitors[0].name == "RivalCo"
    assert trends.competitors[0].points == [100.0, 50.0]


def test_trends_none_point_when_competitor_missing_from_scan(db):
    client = _seed_client(db)
    # First scan ran before the competitor existed
    _seed_scan_with_results(db, client, datetime(2026, 5, 1), client_detected=2)
    comp = Competitor(client_id=client.id, name="RivalCo")
    db.add(comp)
    db.commit()
    _seed_scan_with_results(db, client, datetime(2026, 6, 1), client_detected=2, comp_detected=4, competitor=comp)

    trends = compute_competitor_trends(client.id, db)
    assert trends.competitors[0].points == [None, 100.0]


def test_trends_caps_at_limit_keeping_newest(db):
    client = _seed_client(db)
    base = datetime(2026, 1, 1)
    for i in range(15):
        _seed_scan_with_results(db, client, base + timedelta(days=i), client_detected=i % 5)

    trends = compute_competitor_trends(client.id, db, limit=12)
    assert len(trends.scans) == 12
    # newest scan retained, oldest three dropped
    assert trends.scans[-1].completed_at == base + timedelta(days=14)
    assert trends.scans[0].completed_at == base + timedelta(days=3)


def test_trends_empty_without_scans(db):
    client = _seed_client(db)
    trends = compute_competitor_trends(client.id, db)
    assert trends.scans == []
    assert trends.client.points == []
    assert trends.competitors == []


def test_trends_ignores_non_completed_scans(db):
    client = _seed_client(db)
    _seed_scan_with_results(db, client, datetime(2026, 5, 1), client_detected=2)
    failed = Scan(client_id=client.id, status="failed", completed_at=datetime(2026, 6, 1))
    db.add(failed)
    db.commit()

    trends = compute_competitor_trends(client.id, db)
    assert len(trends.scans) == 1
