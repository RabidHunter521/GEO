from datetime import date

from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client


def test_snapshot_source_defaults_manual_and_breakdown_roundtrips(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    snap = AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1), ai_visitors=200,
                             breakdown={"chatgpt.com": 140, "perplexity.ai": 60})
    db.add(snap)
    db.commit()
    row = db.query(AiTrafficSnapshot).one()
    assert row.source == "manual"
    assert row.breakdown["chatgpt.com"] == 140


def test_client_ga4_property_id_nullable(db):
    c = Client(name="A", website="https://a.my", industry="x", ga4_property_id="123456789")
    db.add(c)
    db.commit()
    assert db.query(Client).one().ga4_property_id == "123456789"
