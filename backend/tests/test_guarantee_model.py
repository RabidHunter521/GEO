from datetime import date

from app.models.client import Client
from app.models.guarantee import Guarantee


def test_guarantee_roundtrip(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    g = Guarantee(client_id=c.id, metric="ai_citability", baseline_value=38,
                  target_value=55, start_date=date(2026, 7, 1),
                  deadline_date=date(2026, 9, 29))
    db.add(g)
    db.commit()
    row = db.query(Guarantee).one()
    assert row.status == "active"
    assert row.last_state is None
