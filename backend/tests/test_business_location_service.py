"""Business location service invariants and schema validation."""

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.dialects import postgresql


def _make_client(db, name="Acme Dental"):
    from app.models.client import Client

    client = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    db.add(client)
    db.commit()
    return client


def _payload(name="Orchard Clinic", **overrides):
    from app.schemas.business_location import BusinessLocationCreate

    body = {
        "name": name,
        "country": "SG",
        "latitude": 1.3048,
        "longitude": 103.8318,
    }
    body.update(overrides)
    return BusinessLocationCreate(**body)


def test_create_location_slugifies_name_and_resolves_client_collisions(db):
    from app.services.business_location_service import create_location

    account = _make_client(db)

    first = create_location(account.id, _payload(), db)
    second = create_location(account.id, _payload(), db)

    assert first.slug == "orchard-clinic"
    assert second.slug == "orchard-clinic-2"


def test_setting_a_primary_location_reassigns_it_within_the_client(db):
    from app.schemas.business_location import BusinessLocationPatch
    from app.services.business_location_service import create_location, patch_location

    account = _make_client(db)
    first = create_location(account.id, _payload("Orchard", is_primary=True), db)
    second = create_location(account.id, _payload("Tampines"), db)

    reassigned = patch_location(second, BusinessLocationPatch(is_primary=True), db)
    db.refresh(first)

    assert reassigned.is_primary is True
    assert first.is_primary is False


def test_location_reads_are_client_scoped_and_list_active_locations_by_default(db):
    from app.services.business_location_service import (
        create_location,
        deactivate_location,
        get_location,
        list_locations,
    )

    account = _make_client(db)
    other = _make_client(db, "Bravo Legal")
    primary = create_location(account.id, _payload("Orchard", is_primary=True), db)
    inactive = create_location(account.id, _payload("Tampines"), db)
    deactivate_location(inactive, db)

    assert get_location(other.id, primary.id, db) is None
    assert list_locations(account.id, db) == [primary]
    assert list_locations(account.id, db, active=False) == [inactive]


def test_deactivation_is_soft_and_rejects_the_only_active_location(db):
    from app.services.business_location_service import (
        BusinessLocationValidationError,
        create_location,
        deactivate_location,
    )

    account = _make_client(db)
    primary = create_location(account.id, _payload("Orchard", is_primary=True), db)
    secondary = create_location(account.id, _payload("Tampines"), db)

    deactivated = deactivate_location(secondary, db)

    assert deactivated.active is False
    assert db.get(type(secondary), secondary.id) is not None
    with pytest.raises(BusinessLocationValidationError, match="only active"):
        deactivate_location(primary, db)


def test_deactivating_a_primary_requires_and_atomically_promotes_an_active_replacement(db):
    from app.services.business_location_service import (
        BusinessLocationValidationError,
        create_location,
        deactivate_location,
    )

    account = _make_client(db)
    primary = create_location(account.id, _payload("Orchard", is_primary=True), db)
    replacement = create_location(account.id, _payload("Tampines"), db)
    inactive = create_location(account.id, _payload("Punggol"), db)
    deactivate_location(inactive, db)

    with pytest.raises(BusinessLocationValidationError, match="replacement"):
        deactivate_location(primary, db)
    with pytest.raises(BusinessLocationValidationError, match="Replacement location"):
        deactivate_location(primary, db, replacement_location_id=inactive.id)

    deactivated = deactivate_location(primary, db, replacement_location_id=replacement.id)
    db.refresh(replacement)

    assert deactivated.active is False
    assert deactivated.is_primary is False
    assert replacement.active is True
    assert replacement.is_primary is True


def test_deactivation_locks_all_active_client_locations_before_counting(db):
    from app.services.business_location_service import create_location, deactivate_location

    account = _make_client(db)
    create_location(account.id, _payload("Orchard", is_primary=True), db)
    secondary = create_location(account.id, _payload("Tampines"), db)
    statements = []

    def capture_statement(_conn, clauseelement, *_args):
        statements.append(str(clauseelement.compile(dialect=postgresql.dialect())))

    event.listen(db.bind, "before_execute", capture_statement)
    try:
        deactivate_location(secondary, db)
    finally:
        event.remove(db.bind, "before_execute", capture_statement)

    assert any(
        "FROM business_locations" in statement
        and "business_locations.active IS true" in statement
        and "FOR UPDATE" in statement
        for statement in statements
    )


def test_location_schema_rejects_invalid_geography_country_and_hours():
    from app.schemas.business_location import BusinessLocationCreate

    with pytest.raises(ValidationError, match="country"):
        BusinessLocationCreate(name="Orchard", country="Singapore")
    with pytest.raises(ValidationError, match="less than or equal to 90"):
        BusinessLocationCreate(name="Orchard", latitude=90.1)
    with pytest.raises(ValidationError, match="less than or equal to 180"):
        BusinessLocationCreate(name="Orchard", longitude=180.1)
    with pytest.raises(ValidationError, match="seven day"):
        BusinessLocationCreate(name="Orchard", hours_json={"monday": []})
    with pytest.raises(ValidationError, match="open"):
        BusinessLocationCreate(
            name="Orchard",
            hours_json={
                day: [{"open": "18:00", "close": "09:00"}]
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
            },
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BusinessLocationCreate(name="Orchard", unexpected="value")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BusinessLocationCreate(
            name="Orchard",
            hours_json={
                day: [{"open": "09:00", "close": "17:00", "label": "Morning"}]
                for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
            },
        )
