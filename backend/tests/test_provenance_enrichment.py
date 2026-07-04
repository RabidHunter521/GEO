import uuid
from unittest.mock import patch

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import provenance_service as ps
from app.services.url_safety import SafeResponse, UnsafeUrlError


def _setup(db, urls):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
                    industry="dentist", enabled_platforms=["perplexity"])
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival", website="https://rival.com")
    db.add_all([client, comp])
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed")
    db.add(scan)
    sqr = ScanQueryResult(scan_id=scan.id, platform="perplexity", category="recommendation",
                          query_text="best crm", response_text="…", brand_detected=False)
    for i, u in enumerate(urls, start=1):
        sqr.sources.append(ScanQuerySource(url=u, domain=ps.normalize_domain(u), title=None, rank=i))
    db.add(sqr)
    db.commit()
    return client, comp, scan


def test_third_party_presence_from_page_text(db):
    _setup(db, ["https://g2.com/crm"])
    page = SafeResponse(status_code=200, text="<p>Rival is the top pick.</p>",
                        headers={"content-type": "text/html"})
    with patch.object(ps, "safe_get", return_value=page):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    row = db.query(ScanQuerySource).one()
    assert row.source_type == "third_party"
    assert row.fetch_status == "ok"
    assert row.present_brands["client"] is False
    assert row.present_brands["competitors"] == [str(_comp_id(db))]


def test_owned_domains_need_no_fetch(db):
    client, comp, _ = _setup(db, ["https://acme.com/pricing", "https://rival.com/home"])
    called = []
    with patch.object(ps, "safe_get", side_effect=lambda *a, **k: called.append(1)):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    assert called == []  # owned domains classified without fetching
    rows = {r.domain: r for r in db.query(ScanQuerySource).all()}
    assert rows["acme.com"].source_type == "client_owned"
    assert rows["acme.com"].present_brands == {"client": True, "competitors": []}
    assert rows["rival.com"].source_type == "competitor_owned"
    assert rows["rival.com"].present_brands == {"client": False, "competitors": [str(comp.id)]}


def test_blocked_url_fails_open(db):
    _setup(db, ["https://internal.evil/x"])
    with patch.object(ps, "safe_get", side_effect=UnsafeUrlError("nope")):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    row = db.query(ScanQuerySource).one()
    assert row.fetch_status == "blocked"
    assert row.present_brands is None


def test_duplicate_url_fetched_once(db):
    _setup(db, ["https://g2.com/crm", "https://g2.com/crm"])
    page = SafeResponse(status_code=200, text="Acme rocks", headers={"content-type": "text/html"})
    calls = []
    def _fake_get(url, **kw):
        calls.append(url)
        return page
    with patch.object(ps, "safe_get", side_effect=_fake_get):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    assert len(calls) == 1
    rows = db.query(ScanQuerySource).all()
    assert all(r.fetch_status == "ok" for r in rows)


def _latest_scan_id(db):
    return db.query(Scan).first().id


def _comp_id(db):
    return db.query(Competitor).first().id
