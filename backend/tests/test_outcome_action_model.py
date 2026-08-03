"""OutcomeAction persistence."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError


def _make_client(db):
    from app.models.client import Client

    client = Client(
        name="Acme Dental",
        website="https://acme.com",
        industry="Dental clinic",
        contact_email="hello@acme.com",
    )
    db.add(client)
    db.commit()
    return client


def _make_action(client_id):
    from app.models.outcome_action import OutcomeAction

    return OutcomeAction(
        client_id=client_id,
        action_type="content",
        title="Publish emergency plumbing page",
        rationale="High-intent query is currently won by two competitors.",
        priority="high",
        confidence="repeated",
        status="recommended",
        source_kind="content_gap",
        source_ref="content_gap:abc",
    )


def test_outcome_action_round_trip_defaults_and_optional_references(db):
    client = _make_client(db)
    action = _make_action(client.id)
    action.priority_score = 90
    action.priority_reasons = ["Repeated competitor win"]
    action.due_date = date(2026, 8, 15)
    action.client_safe_summary = "Create a page for emergency plumbing searches."
    action.approval_token_hash = "sha256:stored-hash-only"

    db.add(action)
    db.commit()

    from app.models.outcome_action import OutcomeAction

    row = db.query(OutcomeAction).one()
    assert row.client_id == client.id
    assert row.action_type == "content"
    assert row.title == "Publish emergency plumbing page"
    assert row.source_ref == "content_gap:abc"
    assert row.scan_id is None
    assert row.work_log_entry_id is None
    assert row.content_deliverable_id is None
    assert row.priority_score == 90
    assert row.priority_reasons == ["Repeated competitor win"]
    assert row.status == "recommended"
    assert row.created_at is not None
    assert row.updated_at is not None
    assert row.approval_token_hash == "sha256:stored-hash-only"


def test_outcome_action_persists_structured_verification_evidence(db):
    client = _make_client(db)
    action = _make_action(client.id)
    action.verification_result = {
        "scan_id": "c2c67ef5-620b-4755-a54d-c24e57ae583a",
        "basis": "visibility_change",
    }
    db.add(action)
    db.commit()

    from app.models.outcome_action import OutcomeAction

    assert db.query(OutcomeAction).one().verification_result == {
        "scan_id": "c2c67ef5-620b-4755-a54d-c24e57ae583a",
        "basis": "visibility_change",
    }


def test_outcome_action_requires_client_and_client_safe_fields(db):
    from app.models.outcome_action import OutcomeAction

    action = OutcomeAction(
        action_type="content",
        title="Publish emergency plumbing page",
        rationale="High-intent query is currently won by two competitors.",
        priority="high",
        confidence="repeated",
        source_kind="content_gap",
        source_ref="content_gap:missing-client",
    )
    db.add(action)

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_outcome_action_unique_client_source_ref(db):
    client = _make_client(db)
    db.add(_make_action(client.id))
    db.commit()

    db.add(_make_action(client.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_outcome_action_allows_null_source_ref(db):
    client = _make_client(db)
    first = _make_action(client.id)
    first.source_ref = None
    second = _make_action(client.id)
    second.source_ref = None

    db.add_all([first, second])
    db.commit()

    from app.models.outcome_action import OutcomeAction

    assert db.query(OutcomeAction).count() == 2


def test_outcome_action_is_deleted_with_its_client(db):
    client = _make_client(db)
    db.add(_make_action(client.id))
    db.commit()

    db.delete(client)
    db.commit()

    from app.models.outcome_action import OutcomeAction

    assert db.query(OutcomeAction).count() == 0


def test_deleting_location_unscopes_outcome_action_without_deleting_it(db):
    from app.models.business_location import BusinessLocation
    from app.models.outcome_action import OutcomeAction

    client = _make_client(db)
    location = BusinessLocation(
        client_id=client.id,
        name="Orchard",
        slug="orchard",
        is_primary=True,
    )
    db.add(location)
    db.flush()

    action = _make_action(client.id)
    action.location_id = location.id
    db.add(action)
    db.commit()

    db.delete(location)
    db.commit()

    persisted_action = db.query(OutcomeAction).one()
    assert persisted_action.client_id == client.id
    assert persisted_action.location_id is None
