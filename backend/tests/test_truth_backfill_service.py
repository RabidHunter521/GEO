"""Idempotent repair backfill for legacy Client fields."""


def _make_client(db, **overrides):
    from app.models.client import Client

    values = {
        "name": "Acme Dental",
        "website": "https://acme.example",
        "industry": "Dental clinic",
        "description": "Family dentistry in Singapore.",
        "phone": "+65 6123 4567",
        "city": "Singapore",
        "state": "Singapore",
        "country": "SG",
    }
    values.update(overrides)
    client = Client(**values)
    db.add(client)
    db.commit()
    return client


def test_backfill_is_idempotent_and_creates_approved_truth_for_current_client_data(db):
    """Removing the duplicate guards would create a second location, fact, or version."""
    from app.models.business_location import BusinessLocation
    from app.models.truth_fact import TruthFact, TruthFactVersion
    from app.services.truth_backfill_service import backfill_client_truth

    client = _make_client(db)

    first = backfill_client_truth(client.id, db)
    second = backfill_client_truth(client.id, db)

    locations = db.query(BusinessLocation).filter_by(client_id=client.id).all()
    facts = db.query(TruthFact).filter_by(client_id=client.id).all()
    versions = db.query(TruthFactVersion).join(TruthFact).filter(TruthFact.client_id == client.id).all()

    assert first.locations_created == 1
    assert first.facts_created == 8
    assert first.versions_created == 8
    assert second.locations_created == 0
    assert second.facts_created == 0
    assert second.versions_created == 0
    assert [(location.name, location.slug, location.is_primary) for location in locations] == [
        ("Acme Dental", f"primary-{client.id}", True)
    ]
    assert {(fact.location_id is None, fact.fact_type, fact.fact_key) for fact in facts} == {
        (True, "business", "official_name"),
        (True, "business", "website"),
        (True, "business", "industry"),
        (True, "business", "description"),
        (True, "business", "phone"),
        (False, "location", "city"),
        (False, "location", "state"),
        (False, "location", "country"),
    }
    assert len(versions) == 8
    assert {
        (version.status, version.source_url, version.approved_by, version.effective_from is not None)
        for version in versions
    } == {("approved", "client-record://backfill", "system:migration", True)}
    assert {version.truth_fact_id for version in versions} == {fact.id for fact in facts}


def test_backfill_skips_blank_client_values(db):
    """Removing blank filtering would create empty fact identities and versions."""
    from app.models.business_location import BusinessLocation
    from app.models.truth_fact import TruthFact, TruthFactVersion
    from app.services.truth_backfill_service import backfill_client_truth

    client = _make_client(
        db,
        description="   ",
        phone="",
        city="\t",
        state=None,
        country="",
    )

    result = backfill_client_truth(client.id, db)

    location = db.query(BusinessLocation).filter_by(client_id=client.id, is_primary=True).one()
    facts = db.query(TruthFact).filter_by(client_id=client.id).all()
    versions = db.query(TruthFactVersion).join(TruthFact).filter(TruthFact.client_id == client.id).all()

    assert result.facts_created == 3
    assert result.versions_created == 3
    assert location.city is None
    assert location.state is None
    assert location.country is None
    assert {(fact.fact_type, fact.fact_key) for fact in facts} == {
        ("business", "official_name"),
        ("business", "website"),
        ("business", "industry"),
    }
    assert [version.value_json for version in versions] == [
        {"value": "Acme Dental", "display_value": "Acme Dental"},
        {"value": "https://acme.example", "display_value": "https://acme.example"},
        {"value": "Dental clinic", "display_value": "Dental clinic"},
    ]
