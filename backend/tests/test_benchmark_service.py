# backend/tests/test_benchmark_service.py
import uuid
from datetime import datetime

from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.services.benchmark_service import compute_industry_benchmark, compute_percentile


# ── compute_percentile (pure math) ────────────────────────────────────────────

def test_percentile_best_of_five_is_top_20():
    ids = [uuid.uuid4() for _ in range(5)]
    scores = dict(zip(ids, [90.0, 80.0, 70.0, 60.0, 50.0]))
    assert compute_percentile(scores, ids[0]) == (1, 20)


def test_percentile_worst_of_four_is_top_100():
    ids = [uuid.uuid4() for _ in range(4)]
    scores = dict(zip(ids, [90.0, 80.0, 70.0, 10.0]))
    assert compute_percentile(scores, ids[3]) == (4, 100)


def test_percentile_ties_share_better_rank():
    ids = [uuid.uuid4() for _ in range(3)]
    scores = dict(zip(ids, [80.0, 80.0, 50.0]))
    assert compute_percentile(scores, ids[0]) == (1, 34)  # ceil(1/3*100)
    assert compute_percentile(scores, ids[1]) == (1, 34)


def test_percentile_none_when_client_missing():
    assert compute_percentile({uuid.uuid4(): 50.0}, uuid.uuid4()) is None


# ── compute_industry_benchmark (DB) ───────────────────────────────────────────

def _seed_scored_client(db, name, industry, score, archived=False):
    client = Client(
        name=name, website=f"https://{name.lower().replace(' ', '')}.example",
        industry=industry,
        archived_at=datetime(2026, 1, 1) if archived else None,
    )
    db.add(client)
    db.commit()
    scan = Scan(client_id=client.id, status="completed", completed_at=datetime(2026, 6, 1))
    db.add(scan)
    db.commit()
    db.add(GeoScore(client_id=client.id, scan_id=scan.id, overall_score=score,
                    computed_at=datetime(2026, 6, 1)))
    db.commit()
    return client


def test_benchmark_returns_percentile_and_average(db):
    a = _seed_scored_client(db, "Alpha", "Technology", 90.0)
    _seed_scored_client(db, "Beta", "Technology", 70.0)
    _seed_scored_client(db, "Gamma", "Technology", 50.0)

    result = compute_industry_benchmark(a, db)
    assert result is not None
    assert result.peer_count == 3
    assert result.rank == 1
    assert result.top_percent == 34  # ceil(1/3*100)
    assert result.industry_average == 70.0
    assert result.client_score == 90.0


def test_benchmark_none_below_min_peers(db):
    a = _seed_scored_client(db, "Alpha", "Technology", 90.0)
    _seed_scored_client(db, "Beta", "Technology", 70.0)
    assert compute_industry_benchmark(a, db) is None


def test_benchmark_excludes_archived_and_other_industries(db):
    a = _seed_scored_client(db, "Alpha", "Technology", 90.0)
    _seed_scored_client(db, "Beta", "Technology", 70.0)
    _seed_scored_client(db, "Archived", "Technology", 60.0, archived=True)
    _seed_scored_client(db, "Foodie", "Food & Beverage", 80.0)
    # only 2 valid Technology peers → hidden
    assert compute_industry_benchmark(a, db) is None


def test_benchmark_industry_match_is_case_and_whitespace_insensitive(db):
    a = _seed_scored_client(db, "Alpha", "Technology", 90.0)
    _seed_scored_client(db, "Beta", " technology ", 70.0)
    _seed_scored_client(db, "Gamma", "TECHNOLOGY", 50.0)

    result = compute_industry_benchmark(a, db)
    assert result is not None
    assert result.peer_count == 3


def test_benchmark_none_when_client_unscored(db):
    unscored = Client(name="NoScan", website="https://noscan.example", industry="Technology")
    db.add(unscored)
    db.commit()
    _seed_scored_client(db, "Alpha", "Technology", 90.0)
    _seed_scored_client(db, "Beta", "Technology", 70.0)
    _seed_scored_client(db, "Gamma", "Technology", 50.0)
    assert compute_industry_benchmark(unscored, db) is None


def test_benchmark_uses_latest_score_per_client(db):
    a = _seed_scored_client(db, "Alpha", "Technology", 40.0)
    # newer score for Alpha
    scan2 = Scan(client_id=a.id, status="completed", completed_at=datetime(2026, 6, 10))
    db.add(scan2)
    db.commit()
    db.add(GeoScore(client_id=a.id, scan_id=scan2.id, overall_score=95.0,
                    computed_at=datetime(2026, 6, 10)))
    db.commit()
    _seed_scored_client(db, "Beta", "Technology", 70.0)
    _seed_scored_client(db, "Gamma", "Technology", 50.0)

    result = compute_industry_benchmark(a, db)
    assert result.client_score == 95.0
    assert result.rank == 1
