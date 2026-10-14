"""Measured criteria of the Brand Authority / Content Quality checklist.

Same data in, same points out: each criterion is computed from rows SeenBy
holds, and missing data scores 0 with a hint rather than a guess.
"""
from datetime import datetime, timedelta

from app.services import assessment_rubric


def _client(db, **kw):
    from app.models.client import Client

    c = Client(name="Acme Dental", website="https://acme.example", industry="Dental", **kw)
    db.add(c)
    db.commit()
    return c


def _by_key(rows):
    return {r["key"]: r for r in rows}


def test_bare_client_scores_zero_with_a_hint_everywhere(db):
    c = _client(db)
    for dimension in ("brand_authority", "content_quality"):
        for row in assessment_rubric.measure(c, dimension, db):
            assert row["points"] == 0 and row["evidence"] is None and row["admin_hint"], row


def test_directory_presence_counts_verified_full_and_live_half(db):
    from app.models.authority_asset import AuthorityAsset

    c = _client(db)  # no pack: DEFAULT_CORE_AUTHORITY_ASSETS (4 listings)
    db.add_all([
        AuthorityAsset(client_id=c.id, asset_key="gbp", name="Google Business Profile",
                       asset_type="review_platform", status="verified"),
        AuthorityAsset(client_id=c.id, asset_key="facebook", name="Facebook page",
                       asset_type="social", status="live"),
        AuthorityAsset(client_id=c.id, asset_key="clutch", name="Clutch",
                       asset_type="directory", status="verified"),  # not a core listing
    ])
    db.commit()
    row = _by_key(assessment_rubric.measure(c, "brand_authority", db))["directory_presence"]
    assert row["points"] == round(25 * 1.5 / 4)
    assert "1 of 4 key listings verified (Google Business Profile)" in row["evidence"]


def test_ai_source_presence_scales_to_40_percent(db):
    from app.models.scan import Scan
    from app.models.share_of_source_snapshot import ShareOfSourceSnapshot

    c = _client(db)
    scan = Scan(client_id=c.id, platform="multi", status="completed", completed_at=datetime(2026, 9, 1))
    db.add(scan)
    db.flush()
    db.add(ShareOfSourceSnapshot(client_id=c.id, scan_id=scan.id, total_third_party_sources=50,
                                 client_share_pct=20.0, competitor_shares=[], acquisition_list=[]))
    db.commit()
    row = _by_key(assessment_rubric.measure(c, "brand_authority", db))["ai_source_presence"]
    assert row["points"] == 12  # 25 * 20/40, rounded
    assert "20% of the 50 independent sites" in row["evidence"]


def test_brand_recognition_uses_scored_brand_answers_of_the_latest_scan(db):
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult

    c = _client(db)
    old = Scan(client_id=c.id, platform="multi", status="completed", completed_at=datetime(2026, 8, 1))
    new = Scan(client_id=c.id, platform="multi", status="completed", completed_at=datetime(2026, 9, 1))
    db.add_all([old, new])
    db.flush()

    def add(scan, platform, detected, category="brand"):
        db.add(ScanQueryResult(scan_id=scan.id, platform=platform, competitor_id=None,
                               category=category, query_text="What is Acme Dental?",
                               response_text="x", brand_detected=detected))

    add(old, "chatgpt", False)
    add(new, "chatgpt", True)
    add(new, "claude", True)
    add(new, "gemini", False)
    add(new, "google_aio", True)               # reported-only: excluded
    add(new, "chatgpt", True, "recommendation")  # not a brand question: excluded
    db.commit()
    row = _by_key(assessment_rubric.measure(c, "brand_authority", db))["brand_recognition"]
    assert row["points"] == 10  # 15 * 2/3
    assert "2 of 3 answers" in row["evidence"]


def test_reviews_combine_volume_and_rating_from_the_latest_snapshots(db):
    from app.models.authority_asset import AuthorityAsset

    c = _client(db)
    db.add(AuthorityAsset(
        client_id=c.id, asset_key="gbp", name="Google Business Profile",
        asset_type="review_platform", status="verified",
        review_snapshots=[{"date": "2026-08-01", "rating": 3.0, "count": 10},
                          {"date": "2026-09-01", "rating": 4.6, "count": 200}],
    ))
    db.commit()
    row = _by_key(assessment_rubric.measure(c, "brand_authority", db))["reviews"]
    assert row["points"] == 15  # full volume (200) + top rating band
    assert row["evidence"] == "200 public reviews averaging 4.6 stars."


def test_page_readability_averages_the_latest_audit_per_page(db):
    from app.models.page_audit import PageAudit

    c = _client(db)
    t = datetime(2026, 9, 1)
    db.add_all([
        PageAudit(client_id=c.id, url="https://acme.example/", score=40, checks=[], suggestions=[],
                  created_at=t),
        PageAudit(client_id=c.id, url="https://acme.example/", score=80, checks=[], suggestions=[],
                  created_at=t + timedelta(days=1)),  # latest for this page wins
        PageAudit(client_id=c.id, url="https://acme.example/braces", score=60, checks=[],
                  suggestions=[], created_at=t),
    ])
    db.commit()
    row = _by_key(assessment_rubric.measure(c, "content_quality", db))["page_readability"]
    assert row["points"] == 28  # 40 * 70/100
    assert "average 70/100" in row["evidence"] and "2 pages" in row["evidence"]
    assert row["admin_hint"]  # fewer than 3 pages audited


def test_topic_coverage_and_depth_read_the_latest_content_analysis(db):
    from app.models.content_analysis import ContentAnalysis

    c = _client(db)
    db.add(ContentAnalysis(
        client_id=c.id, status="completed", pages_crawled=10, entity_coverage_score=50.0,
        content_metrics_json={"faq_count": 2, "blog_count": 4, "word_count": 3000},
        analyzed_at=datetime(2026, 9, 1),
    ))
    db.commit()
    rows = _by_key(assessment_rubric.measure(c, "content_quality", db))
    assert rows["topic_coverage"]["points"] == 10
    # FAQ 6 + 3+ articles 7 + 300 words/page 4 = 17 of 20
    assert rows["content_depth"]["points"] == 17
    assert "2 FAQ sections, 4 articles, about 300 words per page" in rows["content_depth"]["evidence"]


def test_client_evidence_never_uses_banned_terms():
    import inspect
    import re

    source = inspect.getsource(assessment_rubric).lower()
    for banned in ("cited", "citation", "mentioned", "ranking position", "confidence"):
        assert not re.search(rf"\b{banned}\b", source), banned
