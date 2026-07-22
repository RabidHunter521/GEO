import uuid

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import provenance_service as ps


def _seed_enriched(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival", website="https://rival.com")
    db.add_all([client, comp])
    from datetime import datetime
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
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
    from datetime import datetime
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
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
