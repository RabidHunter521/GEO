from datetime import date, timedelta

import pytest

from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee
from app.models.scan import Scan
from app.services.guarantee_service import (
    create_guarantee, derive_state, get_guarantee_progress, resolve_guarantee,
)


def _client_with_score(db, citability=40.0, overall=50.0):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed")
    db.add(s)
    db.commit()
    db.add(GeoScore(client_id=c.id, scan_id=s.id, ai_citability=citability,
                    brand_authority=50.0, content_quality=50.0,
                    technical_foundations=0.0, structured_data=0.0,
                    overall_score=overall))
    db.commit()
    return c


def _g(baseline=40, target=60, start=None, deadline=None):
    start = start or date.today() - timedelta(days=30)
    deadline = deadline or date.today() + timedelta(days=60)
    return Guarantee(metric="ai_citability", baseline_value=baseline, target_value=target,
                     start_date=start, deadline_date=deadline, status="active")


def test_create_autofills_baseline_and_blocks_duplicate(db):
    c = _client_with_score(db, citability=42.4)
    g = create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db)
    assert g.baseline_value == 42
    with pytest.raises(ValueError):
        create_guarantee(c.id, "ai_citability", 65, date.today() + timedelta(days=90), db)


def test_create_without_score_requires_override(db):
    c = Client(name="B", website="https://b.my", industry="x")
    db.add(c)
    db.commit()
    with pytest.raises(ValueError):
        create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db)
    g = create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db,
                         baseline_override=35)
    assert g.baseline_value == 35


def test_derive_states():
    today = date.today()
    # met early
    assert derive_state(_g(), 61.0, today) == "met"
    # grace window: 5 days into 100 → never at_risk
    g = _g(start=today - timedelta(days=5), deadline=today + timedelta(days=95))
    assert derive_state(g, 40.0, today) == "on_track"
    # behind pace at 50% elapsed with 0 gained
    g = _g(start=today - timedelta(days=45), deadline=today + timedelta(days=45))
    assert derive_state(g, 40.0, today) == "at_risk"
    # ahead of pace
    assert derive_state(g, 52.0, today) == "on_track"
    # past deadline, unmet
    g = _g(start=today - timedelta(days=100), deadline=today - timedelta(days=1))
    assert derive_state(g, 50.0, today) == "deadline_passed"


def test_resolve_locks(db):
    c = _client_with_score(db)
    g = create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db)
    resolve_guarantee(g.id, "void", db, note="client paused")
    assert g.status == "void" and g.resolved_at is not None
    with pytest.raises(ValueError):
        resolve_guarantee(g.id, "met", db)


def test_progress_none_without_guarantee(db):
    c = _client_with_score(db)
    assert get_guarantee_progress(c.id, db) is None


def test_progress_fields(db):
    c = _client_with_score(db, citability=48.0)
    create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db,
                     baseline_override=40, start_date=date.today() - timedelta(days=10))
    p = get_guarantee_progress(c.id, db)
    assert p.current_value == 48.0
    assert p.points_needed == 20
    assert p.points_gained == 8.0
    assert p.days_total == 100
    assert p.days_remaining == 90
