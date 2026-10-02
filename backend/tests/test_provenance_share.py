import uuid
from datetime import datetime, timedelta

from app.core.constants import SOURCE_CAPTURE_VERSION
from app.models.activity_log import ActivityLog
from app.models.share_of_source_snapshot import ShareOfSourceSnapshot
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import provenance_service as ps
from app.core.time import utcnow


def _seed_enriched(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival", website="https://rival.com")
    db.add_all([client, comp])
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    sqr = ScanQueryResult(scan_id=scan.id, platform="perplexity", category="recommendation",
                          query_text="best crm", response_text="…", brand_detected=False)
    # g2: competitor present, client absent, cited twice
    for rank in (1, 2):
        sqr.sources.append(ScanQuerySource(
            url="https://g2.com/crm", domain="g2.com", title="G2 CRMs", rank=rank,
            source_type="third_party", fetch_status="ok",
            present_brands={"client": False, "competitors": [str(comp.id)]}))
    # capterra: client present, cited once
    sqr.sources.append(ScanQuerySource(
        url="https://capterra.com/x", domain="capterra.com", title="Capterra", rank=3,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": []}))
    db.add(sqr)
    db.commit()
    return client, comp


def test_share_of_source_and_acquisition(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    resp = ps.compute_share_of_source(client.id, db)

    assert resp.total_third_party_sources == 2  # unique URLs
    assert resp.client_share.sources_present == 1
    assert resp.client_share.share_pct == 50.0
    assert resp.competitor_shares[0].sources_present == 1
    assert resp.competitor_shares[0].share_pct == 50.0

    # acquisition: g2 only (client absent, competitor present), citation_count 2
    assert len(resp.acquisition_list) == 1
    top = resp.acquisition_list[0]
    assert top.domain == "g2.com"
    assert top.citation_count == 2
    assert top.competitors_present[0].name == "Rival"
    assert resp.flip_targets == resp.acquisition_list[:3]


def test_no_scan_returns_empty(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()
    resp = ps.compute_share_of_source(client.id, db)
    assert resp.last_scan_at is None
    assert resp.total_third_party_sources == 0
    assert resp.acquisition_list == []


def test_normalize_domain_strips_www_and_scheme():
    assert ps.normalize_domain("https://www.Acme.com/best-crm") == "acme.com"
    assert ps.normalize_domain("http://blog.acme.com/x") == "blog.acme.com"
    assert ps.normalize_domain("acme.com") == "acme.com"


def test_normalize_domain_handles_garbage():
    assert ps.normalize_domain("") == ""
    assert ps.normalize_domain("not a url") == ""


def test_classify_source_type():
    comp_domains = {"rival.com": "comp-1"}
    assert ps.classify_source_type("acme.com", "acme.com", comp_domains) == "client_owned"
    assert ps.classify_source_type("rival.com", "acme.com", comp_domains) == "competitor_owned"
    assert ps.classify_source_type("g2.com", "acme.com", comp_domains) == "third_party"


def test_persist_snapshot_matches_live_compute(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    live = ps.compute_share_of_source(client.id, db)
    snapshot = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert snapshot is not None
    assert snapshot.scan_id == scan.id
    assert snapshot.client_id == client.id
    assert snapshot.total_third_party_sources == live.total_third_party_sources
    assert snapshot.client_share_pct == live.client_share.share_pct
    assert len(snapshot.acquisition_list) == len(live.acquisition_list)
    assert snapshot.acquisition_list[0]["domain"] == live.acquisition_list[0].domain
    assert snapshot.acquisition_list[0]["citation_count"] == live.acquisition_list[0].citation_count


def test_persist_snapshot_no_third_party_sources_returns_none(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()

    result = ps.compute_and_persist_snapshot(scan.id, client.id, db)
    assert result is None
    assert db.query(ps.ShareOfSourceSnapshot).count() == 0


def test_persist_snapshot_swallows_internal_failure(db, monkeypatch):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    monkeypatch.setattr(ps, "_summarize", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    result = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert result is None
    assert db.query(ps.ShareOfSourceSnapshot).count() == 0


def _seed_second_scan_client_now_present(db, client, comp):
    """Same client/comp as _seed_enriched, but a NEW scan where the client is
    now present at the g2.com URL that was previously an acquisition target."""
    scan2 = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan2)
    sqr2 = ScanQueryResult(scan_id=scan2.id, platform="perplexity", category="recommendation",
                           query_text="best crm", response_text="…", brand_detected=True)
    sqr2.sources.append(ScanQuerySource(
        url="https://g2.com/crm", domain="g2.com", title="G2 CRMs", rank=1,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": [str(comp.id)]}))
    db.add(sqr2)
    db.commit()
    return scan2


def test_flip_detected_when_client_now_present(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan1 = db.query(Scan).filter(Scan.client_id == client.id).first()
    ps.compute_and_persist_snapshot(scan1.id, client.id, db)  # first snapshot: g2.com is an acquisition target

    scan2 = _seed_second_scan_client_now_present(db, client, comp)
    ps.compute_and_persist_snapshot(scan2.id, client.id, db)

    flips = db.query(ActivityLog).filter(
        ActivityLog.client_id == client.id, ActivityLog.event_type == "citation_flip"
    ).all()
    assert len(flips) == 1
    assert "g2.com" in flips[0].note
    assert client.name in flips[0].note


def test_no_flip_when_url_absent_from_new_scan(db):
    """A URL from the previous snapshot's acquisition list that simply doesn't
    reappear in the new scan is search-result drift, not a verified flip."""
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan1 = db.query(Scan).filter(Scan.client_id == client.id).first()
    ps.compute_and_persist_snapshot(scan1.id, client.id, db)

    # New scan with a completely different, unrelated third-party source —
    # g2.com never shows up at all.
    scan2 = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan2)
    sqr2 = ScanQueryResult(scan_id=scan2.id, platform="perplexity", category="recommendation",
                           query_text="best crm", response_text="…", brand_detected=False)
    sqr2.sources.append(ScanQuerySource(
        url="https://capterra.com/x", domain="capterra.com", title="Capterra", rank=1,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": []}))
    db.add(sqr2)
    db.commit()
    ps.compute_and_persist_snapshot(scan2.id, client.id, db)

    flips = db.query(ActivityLog).filter(ActivityLog.event_type == "citation_flip").all()
    assert len(flips) == 0


def test_first_scan_no_previous_snapshot_no_flip_no_error(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    snapshot = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert snapshot is not None
    flips = db.query(ActivityLog).filter(ActivityLog.event_type == "citation_flip").all()
    assert len(flips) == 0


def test_history_returns_oldest_to_newest_capped_at_limit(db):
    from app.services import provenance_service as ps
    from datetime import datetime, timedelta
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()

    base = datetime(2026, 1, 1)
    for i in range(15):
        scan_id = uuid.uuid4()
        db.add(
            Scan(
                id=scan_id,
                client_id=client.id,
                status="completed",
                completed_at=base + timedelta(days=i),
            )
        )
        snap = ps.ShareOfSourceSnapshot(
            client_id=client.id, scan_id=scan_id,
            computed_at=base + timedelta(days=i),
            total_third_party_sources=i, client_share_pct=float(i),
        )
        db.add(snap)
    db.commit()

    history = ps.get_share_of_source_history(client.id, db)
    assert len(history) == 12
    assert history[0].client_share_pct < history[-1].client_share_pct  # oldest first
    assert history[-1].client_share_pct == 14.0  # newest of the 15 seeded


def test_history_empty_for_client_with_no_snapshots(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()
    assert ps.get_share_of_source_history(client.id, db) == []


# ── Task 8 (all-platform sources): trend comparability ──────────────────────


def test_snapshot_records_capture_version_and_platforms(db):
    client, _ = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()
    # A second platform that was captured but drew on no sources still counts
    # as covered: "no sources" is part of the pool definition.
    db.add(ScanQueryResult(scan_id=scan.id, platform="claude", category="recommendation",
                           query_text="best crm", response_text="…", brand_detected=False,
                           sources_captured=True))
    # Competitor rows never feed share-of-source.
    db.add(ScanQueryResult(scan_id=scan.id, platform="gemini", category="comparison",
                           query_text="acme vs rival", response_text="…", brand_detected=False,
                           competitor_id=db.query(Competitor).first().id, sources_captured=True))
    db.commit()

    snap = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert snap.source_capture_version == SOURCE_CAPTURE_VERSION
    assert snap.source_platforms == ["claude", "perplexity"]


def _snap(version, platforms):
    return ShareOfSourceSnapshot(source_capture_version=version, source_platforms=platforms)


def test_sources_comparable_requires_same_version_and_platforms():
    v2 = SOURCE_CAPTURE_VERSION
    assert ps.sources_comparable(_snap(v2, ["chatgpt", "gemini"]), _snap(v2, ["chatgpt", "gemini"]))
    assert not ps.sources_comparable(_snap("v1", ["perplexity"]), _snap(v2, ["perplexity"]))
    assert not ps.sources_comparable(_snap(v2, ["chatgpt"]), _snap(v2, ["chatgpt", "gemini"]))


def test_history_marks_the_point_where_coverage_changed(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    base = datetime(2026, 9, 1)
    coverage = [("v1", ["perplexity"]), ("v1", ["perplexity"]),
                ("v2", ["chatgpt", "perplexity"]), ("v2", ["chatgpt", "perplexity"])]
    for i, (version, platforms) in enumerate(coverage):
        scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed",
                    completed_at=base + timedelta(days=i))
        db.add(scan)
        db.add(ShareOfSourceSnapshot(
            client_id=client.id, scan_id=scan.id, computed_at=base + timedelta(days=i),
            total_third_party_sources=5, client_share_pct=10.0 * i,
            source_capture_version=version, source_platforms=platforms,
        ))
    db.commit()

    history = ps.get_share_of_source_history(client.id, db)

    assert [p.coverage_changed for p in history] == [False, False, True, False]


# ── Task 10 (all-platform sources): per-platform view for the admin ──────────

def test_share_of_source_breaks_sources_down_by_platform(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=utcnow())
    db.add_all([client, scan])

    def _row(platform, sources):
        sqr = ScanQueryResult(scan_id=scan.id, platform=platform, category="recommendation",
                              query_text="best dentist", response_text="…", brand_detected=False,
                              sources_captured=True)
        for rank, (url, domain, client_present) in enumerate(sources, start=1):
            sqr.sources.append(ScanQuerySource(
                url=url, domain=domain, title=None, rank=rank, source_type="third_party",
                fetch_status="ok", present_brands={"client": client_present, "competitors": []}))
        db.add(sqr)

    _row("gemini", [("https://facebook.com/a", "facebook.com", False),
                    ("https://yelp.com/a", "yelp.com", True)])
    _row("gemini", [("https://facebook.com/a", "facebook.com", False)])
    _row("chatgpt", [("https://forbes.com/a", "forbes.com", False)])
    db.commit()

    resp = ps.compute_share_of_source(client.id, db)
    by = {p.platform: p for p in resp.by_platform}

    assert [p.platform for p in resp.by_platform] == ["chatgpt", "gemini"]
    assert by["gemini"].total_third_party_sources == 2
    assert by["gemini"].client_share_pct == 50.0
    assert [(d.domain, d.answers) for d in by["gemini"].top_domains] == [
        ("facebook.com", 2), ("yelp.com", 1)
    ]
    assert by["chatgpt"].client_share_pct == 0.0
    assert [d.domain for d in by["chatgpt"].top_domains] == ["forbes.com"]


def test_by_platform_is_empty_without_sources(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()
    assert ps.compute_share_of_source(client.id, db).by_platform == []
