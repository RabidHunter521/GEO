from datetime import date, timedelta
from unittest.mock import patch

from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee
from app.models.scan import Scan
from app.services.guarantee_alert import check_guarantee_transition


def _setup(db, citability):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed")
    db.add(s)
    db.commit()
    db.add(GeoScore(client_id=c.id, scan_id=s.id, ai_citability=citability,
                    brand_authority=0.0, content_quality=0.0,
                    technical_foundations=0.0, structured_data=0.0,
                    overall_score=citability))
    g = Guarantee(client_id=c.id, metric="ai_citability", baseline_value=40,
                  target_value=60, start_date=date.today() - timedelta(days=45),
                  deadline_date=date.today() + timedelta(days=45), status="active")
    db.add(g)
    db.commit()
    return c, g


def test_transition_to_at_risk_alerts_once(db):
    c, g = _setup(db, citability=40.0)  # 0 gained at 50% elapsed → at_risk
    with patch("app.services.guarantee_alert._send_admin_alert") as send:
        check_guarantee_transition(c, db)
        check_guarantee_transition(c, db)
    assert send.call_count == 1
    assert g.last_state == "at_risk"


def test_on_track_updates_state_without_alert(db):
    c, g = _setup(db, citability=52.0)  # ahead of pace → on_track
    with patch("app.services.guarantee_alert._send_admin_alert") as send:
        check_guarantee_transition(c, db)
    assert send.call_count == 0
    assert g.last_state == "on_track"


def test_send_failure_is_swallowed(db):
    c, g = _setup(db, citability=40.0)
    with patch("app.services.guarantee_alert._send_admin_alert", side_effect=RuntimeError):
        check_guarantee_transition(c, db)  # must not raise
    assert g.last_state == "at_risk"


def test_no_guarantee_is_noop(db):
    c = Client(name="B", website="https://b.my", industry="x")
    db.add(c)
    db.commit()
    with patch("app.services.guarantee_alert._send_admin_alert") as send:
        check_guarantee_transition(c, db)
    assert send.call_count == 0
