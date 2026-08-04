"""Persistence contracts for the governed query universe (Phase 5 Task 1).

Covers `TrackedQuery` itself (client/location ownership, brand-vs-location
dedup, non-negative weight constraints) and the repeated-sample metadata
added to `ScanQueryResult` (tracked_query_id, sample_index, prompt_version,
model_name, model_version, observed_at).
"""

import pytest
from sqlalchemy.exc import IntegrityError


def _make_client(db, name="Acme Dental"):
    from app.models.client import Client

    client = Client(
        name=name,
        website="https://acme.example",
        industry="Dental clinic",
        contact_email="hello@acme.example",
    )
    db.add(client)
    db.commit()
    return client


def _make_location(client_id, *, name="Orchard", slug="orchard", is_primary=False):
    from app.models.business_location import BusinessLocation

    location = BusinessLocation(
        client_id=client_id,
        name=name,
        slug=slug,
        is_primary=is_primary,
        city="Singapore",
        country="SG",
        active=True,
    )
    return location


def _make_tracked_query(client_id, *, location_id=None, text="best dentist kl", **overrides):
    from app.models.tracked_query import TrackedQuery

    fields = dict(
        client_id=client_id,
        location_id=location_id,
        text=text,
        normalized_text=text.strip().lower(),
        source="admin",
        intent="recommendation",
    )
    fields.update(overrides)
    return TrackedQuery(**fields)


def _make_scan(client_id):
    from app.models.scan import Scan

    return Scan(client_id=client_id)


def test_tracked_query_round_trip_with_defaults(db):
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    query = _make_tracked_query(client.id)
    db.add(query)
    db.commit()

    row = db.query(TrackedQuery).one()
    assert row.client_id == client.id
    assert row.location_id is None
    assert row.text == "best dentist kl"
    assert row.normalized_text == "best dentist kl"
    assert row.source == "admin"
    assert row.intent == "recommendation"
    assert row.buyer_stage is None
    assert row.service_key is None
    # Defaults applied without the caller specifying them.
    assert row.risk_level == "standard"
    assert row.demand_weight == 0.0
    assert row.priority_score == 0.0
    assert row.is_active is True
    assert row.created_at is not None
    assert row.updated_at is not None


def test_tracked_query_belongs_to_a_location_within_its_own_client(db):
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    location = _make_location(client.id, is_primary=True)
    db.add(location)
    db.commit()

    query = _make_tracked_query(
        client.id, location_id=location.id, text="best dentist orchard", buyer_stage="decision"
    )
    db.add(query)
    db.commit()

    row = db.query(TrackedQuery).one()
    assert row.location_id == location.id
    assert row.buyer_stage == "decision"


def test_tracked_query_rejects_location_owned_by_another_client(db):
    client_a = _make_client(db, name="Acme Dental")
    client_b = _make_client(db, name="Beta Clinic")
    location_b = _make_location(client_b.id, is_primary=True)
    db.add(location_b)
    db.commit()

    # location belongs to client_b, but the query claims client_a — the
    # composite FK (location_id, client_id) -> business_locations(id, client_id)
    # must reject this cross-tenant combination.
    query = _make_tracked_query(client_a.id, location_id=location_b.id)
    db.add(query)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_tracked_query_brand_level_normalized_text_is_unique_per_client(db):
    client = _make_client(db)
    db.add(_make_tracked_query(client.id, text="Best Dentist KL"))
    db.commit()

    db.add(_make_tracked_query(client.id, text="best dentist kl"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_tracked_query_location_level_normalized_text_is_unique_per_location(db):
    client = _make_client(db)
    location = _make_location(client.id, is_primary=True)
    db.add(location)
    db.commit()

    db.add(_make_tracked_query(client.id, location_id=location.id, text="best dentist orchard"))
    db.commit()

    db.add(_make_tracked_query(client.id, location_id=location.id, text="best dentist orchard"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_tracked_query_same_text_allowed_across_brand_and_location_scope(db):
    """Brand-level (location_id NULL) and location-level dedup are separate
    partial unique indexes — a NULL location_id must never collide with the
    location-scoped uniqueness rule, and vice versa."""
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    location = _make_location(client.id, is_primary=True)
    db.add(location)
    db.commit()

    db.add(_make_tracked_query(client.id, text="best dentist kl"))
    db.add(_make_tracked_query(client.id, location_id=location.id, text="best dentist kl"))
    db.commit()

    assert db.query(TrackedQuery).count() == 2


def test_tracked_query_same_text_allowed_across_different_locations(db):
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    orchard = _make_location(client.id, name="Orchard", slug="orchard", is_primary=True)
    tampines = _make_location(client.id, name="Tampines", slug="tampines")
    db.add_all([orchard, tampines])
    db.commit()

    db.add(_make_tracked_query(client.id, location_id=orchard.id, text="best dentist near me"))
    db.add(_make_tracked_query(client.id, location_id=tampines.id, text="best dentist near me"))
    db.commit()

    assert db.query(TrackedQuery).count() == 2


def test_tracked_query_requires_client(db):
    from app.models.tracked_query import TrackedQuery

    query = TrackedQuery(
        text="best dentist kl",
        normalized_text="best dentist kl",
        source="admin",
        intent="recommendation",
    )
    db.add(query)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("field", ["demand_weight", "priority_score"])
def test_tracked_query_rejects_negative_weights(db, field):
    client = _make_client(db)
    query = _make_tracked_query(client.id, **{field: -1.0})
    db.add(query)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_scan_query_result_links_to_tracked_query_and_carries_sample_metadata(db):
    from datetime import datetime
    from app.models.scan_query_result import ScanQueryResult
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    scan = _make_scan(client.id)
    db.add(scan)
    query = _make_tracked_query(client.id)
    db.add(query)
    db.commit()

    observed_at = datetime(2026, 8, 1, 12, 0, 0)
    result = ScanQueryResult(
        scan_id=scan.id,
        category="recommendation",
        query_text=query.text,
        tracked_query_id=query.id,
        sample_index=2,
        prompt_version="v2",
        model_name="gpt-4o",
        model_version="2026-06-01",
        observed_at=observed_at,
    )
    db.add(result)
    db.commit()

    row = db.query(ScanQueryResult).one()
    assert row.tracked_query_id == query.id
    assert row.sample_index == 2
    assert row.prompt_version == "v2"
    assert row.model_name == "gpt-4o"
    assert row.model_version == "2026-06-01"
    assert row.observed_at == observed_at
    assert row.tracked_query.id == query.id

    refreshed_query = db.query(TrackedQuery).one()
    assert [r.id for r in refreshed_query.scan_query_results] == [row.id]


def test_scan_query_result_sample_metadata_defaults_without_a_tracked_query(db):
    from app.models.scan_query_result import ScanQueryResult

    client = _make_client(db)
    scan = _make_scan(client.id)
    db.add(scan)
    db.commit()

    result = ScanQueryResult(
        scan_id=scan.id,
        category="brand",
        query_text="Acme Dental reviews",
    )
    db.add(result)
    db.commit()

    row = db.query(ScanQueryResult).one()
    assert row.tracked_query_id is None
    assert row.sample_index == 1
    assert row.prompt_version == "v1"
    assert row.model_name == "unknown"
    assert row.model_version is None
    assert row.observed_at is not None


def test_scan_query_result_rejects_non_positive_sample_index(db):
    from app.models.scan_query_result import ScanQueryResult

    client = _make_client(db)
    scan = _make_scan(client.id)
    db.add(scan)
    db.commit()

    result = ScanQueryResult(
        scan_id=scan.id,
        category="brand",
        query_text="Acme Dental reviews",
        sample_index=0,
    )
    db.add(result)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_tracked_query_sets_scan_query_result_link_null_not_row(db):
    from app.models.scan_query_result import ScanQueryResult
    from app.models.tracked_query import TrackedQuery

    client = _make_client(db)
    scan = _make_scan(client.id)
    db.add(scan)
    query = _make_tracked_query(client.id)
    db.add(query)
    db.commit()

    result = ScanQueryResult(
        scan_id=scan.id,
        category="recommendation",
        query_text=query.text,
        tracked_query_id=query.id,
    )
    db.add(result)
    db.commit()
    result_id = result.id

    db.delete(query)
    db.commit()

    assert db.query(TrackedQuery).count() == 0
    surviving = db.query(ScanQueryResult).filter_by(id=result_id).one()
    assert surviving.tracked_query_id is None
