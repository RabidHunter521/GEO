"""PlacementTarget model: defaults and one row per (client, URL)."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.constants import PLACEMENT_CATEGORIES, PLACEMENT_STATUSES
from app.models.client import Client
from app.models.placement_target import PlacementTarget


def _client(db) -> Client:
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(c)
    db.commit()
    return c


def test_new_target_defaults(db):
    c = _client(db)
    t = PlacementTarget(client_id=c.id, url="https://best.example/dentists-kl",
                        domain="best.example", category="listicle")
    db.add(t)
    db.commit()
    db.refresh(t)

    assert t.status == "open"
    assert t.answers_count == 0
    assert t.platforms == []
    assert t.query_categories == []
    assert t.competitors_present == []
    assert t.outreach_drafts == []
    assert t.client_present is False
    assert t.priority_score == 0
    assert t.page_analysis is None


def test_one_target_per_client_and_url(db):
    c = _client(db)
    db.add(PlacementTarget(client_id=c.id, url="https://x.example/a", domain="x.example", category="other"))
    db.commit()
    db.add(PlacementTarget(client_id=c.id, url="https://x.example/a", domain="x.example", category="other"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_same_url_allowed_for_different_clients(db):
    a, b = _client(db), _client(db)
    for c in (a, b):
        db.add(PlacementTarget(client_id=c.id, url="https://x.example/a", domain="x.example", category="other"))
    db.commit()
    assert db.query(PlacementTarget).count() == 2


def test_vocabularies():
    assert PLACEMENT_STATUSES == ("open", "pursuing", "placed", "verified", "stale", "dismissed")
    assert "listicle" in PLACEMENT_CATEGORIES and "directory" in PLACEMENT_CATEGORIES
