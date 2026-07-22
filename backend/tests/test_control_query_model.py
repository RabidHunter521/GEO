from app.models.client import Client
from app.models.control_query import ControlQuery
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult


def _client(db):
    c = Client(name="Clinic A", website="https://a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    return c


def test_control_query_roundtrip(db):
    c = _client(db)
    cq = ControlQuery(client_id=c.id, query_text="Best physio in Penang", category="recommendation")
    db.add(cq)
    db.commit()
    row = db.query(ControlQuery).one()
    assert row.active is True
    assert row.query_text == "Best physio in Penang"


def test_scan_query_result_is_control_defaults_false(db):
    c = _client(db)
    s = Scan(client_id=c.id)
    db.add(s)
    db.commit()
    r = ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation", query_text="q")
    db.add(r)
    db.commit()
    assert db.query(ScanQueryResult).one().is_control is False
