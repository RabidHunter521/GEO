import uuid

from app.models.scan import Scan
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(c)
    db.commit()
    return c


def test_sources_cascade_insert_via_relationship(db):
    c = _client(db)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="completed")
    db.add(scan)
    db.commit()

    sqr = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best crm", response_text="…", brand_detected=False,
    )
    sqr.sources.append(
        ScanQuerySource(url="https://x.com/a", domain="x.com", title="A", rank=1)
    )
    db.add(sqr)
    db.commit()

    rows = db.query(ScanQuerySource).all()
    assert len(rows) == 1
    assert rows[0].scan_query_result_id == sqr.id
    assert rows[0].fetch_status == "pending"
    assert rows[0].source_type is None
