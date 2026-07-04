import uuid
from unittest.mock import patch

from app.models.scan import Scan
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import scan_service
from app.services.platform_clients.base import PlatformResult, SourceCitation


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


class _FakePerplexity:
    platform = "perplexity"

    def query(self, prompt):
        return PlatformResult(
            text="Acme is great", model="sonar", input_tokens=1, output_tokens=1,
            citations=(SourceCitation(url="https://g2.com/acme", title="G2", rank=1),),
        )


def test_capture_writes_pending_sources_for_perplexity_client_queries(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
               industry="dentist", enabled_platforms=["perplexity"])
    db.add(c)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="pending")
    db.add(scan)
    db.commit()

    with patch.object(scan_service, "get_platform_client", return_value=_FakePerplexity()), \
         patch.object(scan_service, "record_llm_usage"), \
         patch.object(scan_service, "extract_position", return_value=None), \
         patch("app.services.remediation_service.sync_remediation_items"), \
         patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0):
        scan_service.run_scan(scan.id, db)

    sources = db.query(ScanQuerySource).all()
    assert sources, "expected captured sources"
    assert all(s.fetch_status == "pending" and s.source_type is None for s in sources)
    assert all(s.domain == "g2.com" for s in sources)
