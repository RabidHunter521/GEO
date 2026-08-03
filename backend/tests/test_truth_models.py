"""Persistence contracts for location-scoped and brand-scoped truth."""

from datetime import datetime, timedelta

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


def _make_location(client_id, *, name, slug, is_primary=False):
    from app.models.business_location import BusinessLocation

    return BusinessLocation(
        client_id=client_id,
        name=name,
        slug=slug,
        is_primary=is_primary,
        city="Singapore",
        country="SG",
        active=True,
    )


def test_locations_round_trip_with_one_primary_per_client_and_unique_slugs(db):
    client = _make_client(db)
    primary = _make_location(client.id, name="Orchard", slug="orchard", is_primary=True)
    secondary = _make_location(client.id, name="Tampines", slug="tampines")
    secondary.hours_json = {"mon": "09:00-17:00"}
    secondary.service_area_json = ["Tampines", "Pasir Ris"]

    db.add_all([primary, secondary])
    db.commit()

    from app.models.business_location import BusinessLocation

    rows = db.query(BusinessLocation).order_by(BusinessLocation.slug).all()
    assert [(row.slug, row.is_primary) for row in rows] == [
        ("orchard", True),
        ("tampines", False),
    ]
    assert rows[1].hours_json == {"mon": "09:00-17:00"}
    assert rows[1].service_area_json == ["Tampines", "Pasir Ris"]

    db.add(_make_location(client.id, name="Duplicate", slug="orchard"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(_make_location(client.id, name="Second primary", slug="novena", is_primary=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_truth_facts_keep_brand_and_location_identities_and_version_history(db):
    from app.models.truth_fact import TruthFact, TruthFactVersion

    client = _make_client(db)
    location = _make_location(client.id, name="Orchard", slug="orchard", is_primary=True)
    db.add(location)
    db.commit()

    brand_fact = TruthFact(client_id=client.id, fact_type="business", fact_key="phone")
    location_fact = TruthFact(
        client_id=client.id,
        location_id=location.id,
        fact_type="business",
        fact_key="opening_hours",
    )
    db.add_all([brand_fact, location_fact])
    db.flush()

    effective_from = datetime(2026, 1, 1, 9, 0, 0)
    retired = TruthFactVersion(
        truth_fact_id=location_fact.id,
        value_json={"mon": "09:00-17:00"},
        status="retired",
        effective_from=effective_from,
        effective_to=effective_from + timedelta(days=30),
    )
    approved = TruthFactVersion(
        truth_fact_id=location_fact.id,
        value_json={"mon": "10:00-18:00"},
        status="approved",
        effective_from=effective_from + timedelta(days=31),
        approved_at=effective_from + timedelta(days=31),
        approved_by="reviewer@example.com",
    )
    db.add_all([retired, approved])
    db.commit()

    facts = db.query(TruthFact).order_by(TruthFact.location_id.is_not(None)).all()
    assert [(fact.location_id, fact.fact_key) for fact in facts] == [
        (None, "phone"),
        (location.id, "opening_hours"),
    ]
    versions = db.query(TruthFactVersion).order_by(TruthFactVersion.effective_from).all()
    assert [(version.status, version.effective_to) for version in versions] == [
        ("retired", effective_from + timedelta(days=30)),
        ("approved", None),
    ]

    db.add(TruthFact(client_id=client.id, fact_type="business", fact_key="phone"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(
        TruthFact(
            client_id=client.id,
            location_id=location.id,
            fact_type="business",
            fact_key="opening_hours",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(
        TruthFactVersion(
            truth_fact_id=location_fact.id,
            value_json={"mon": "08:00-16:00"},
            status="approved",
            effective_from=effective_from + timedelta(days=62),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_client_deletion_cascades_to_locations_and_truth(db):
    from app.models.business_location import BusinessLocation
    from app.models.truth_fact import TruthFact, TruthFactVersion

    client = _make_client(db)
    location = _make_location(client.id, name="Orchard", slug="orchard", is_primary=True)
    db.add(location)
    db.flush()
    fact = TruthFact(
        client_id=client.id,
        location_id=location.id,
        fact_type="business",
        fact_key="phone",
    )
    db.add(fact)
    db.flush()
    db.add(TruthFactVersion(truth_fact_id=fact.id, value_json="+65 1234 5678", status="draft"))
    db.commit()

    db.delete(client)
    db.commit()

    assert db.query(BusinessLocation).count() == 0
    assert db.query(TruthFact).count() == 0
    assert db.query(TruthFactVersion).count() == 0
