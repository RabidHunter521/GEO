"""Outcome Action lifecycle and CRUD service."""
from datetime import date

import pytest


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


def _create_payload(source_ref="content_gap:emergency-dental"):
    from app.schemas.outcome_action import OutcomeActionCreate

    return OutcomeActionCreate(
        source_kind="content_gap",
        source_ref=source_ref,
        title="Publish emergency dental page",
        rationale="High-intent emergency searches are currently won by competitors.",
        action_type="content",
        priority="high",
        confidence="repeated",
        client_safe_summary="Create a page for emergency dental searches.",
    )


def test_create_action_and_get_action_are_scoped_to_client(db):
    from app.services.outcome_action_service import create_action, get_action

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")

    action = create_action(client.id, _create_payload(), db)

    assert action.client_id == client.id
    assert action.status == "recommended"
    assert get_action(client.id, action.id, db) == action
    assert get_action(other_client.id, action.id, db) is None


def test_create_action_reuses_existing_client_source_reference(db):
    from app.services.outcome_action_service import create_action

    client = _make_client(db)

    first = create_action(client.id, _create_payload(), db)
    second = create_action(client.id, _create_payload(), db)

    assert second.id == first.id
    assert db.query(type(first)).count() == 1


def test_list_actions_filters_by_client(db):
    from app.services.outcome_action_service import create_action, list_actions

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")
    action = create_action(client.id, _create_payload(), db)
    create_action(other_client.id, _create_payload(), db)

    assert list_actions(client.id, db) == [action]


def test_patch_action_updates_owner_due_date_and_client_safe_fields(db):
    from app.schemas.outcome_action import OutcomeActionPatch
    from app.services.outcome_action_service import create_action, patch_action

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)

    patched = patch_action(
        action,
        OutcomeActionPatch(
            owner="Maya",
            due_date=date(2026, 8, 15),
            client_safe_summary="A reviewed, client-safe summary.",
            destination_url="https://acmedental.example.com/emergency",
            dismissal_reason="Not suitable for this client.",
        ),
        db,
    )

    assert patched.owner == "Maya"
    assert patched.due_date == date(2026, 8, 15)
    assert patched.client_safe_summary == "A reviewed, client-safe summary."
    assert patched.destination_url == "https://acmedental.example.com/emergency"
    assert patched.client_comment == "Not suitable for this client."


def test_transition_from_approved_internal_to_in_progress_sets_updated_timestamp(db):
    from app.core.time import utcnow
    from app.services.outcome_action_service import create_action, transition_action

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)
    action.status = "approved_internal"
    action.updated_at = utcnow()
    db.commit()
    before = action.updated_at

    transitioned = transition_action(action, "in_progress", db)

    assert transitioned.status == "in_progress"
    assert transitioned.updated_at >= before


def test_transition_rejects_invalid_lifecycle_edge(db):
    from app.services.outcome_action_service import (
        InvalidOutcomeTransition,
        create_action,
        transition_action,
    )

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)

    with pytest.raises(InvalidOutcomeTransition):
        transition_action(action, "verified", db)


def test_transition_to_published_requires_destination_url_and_sets_timestamp(db):
    from app.services.outcome_action_service import (
        OutcomeActionValidationError,
        create_action,
        transition_action,
    )

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)
    action.status = "ready_to_publish"
    db.commit()

    with pytest.raises(OutcomeActionValidationError, match="destination_url"):
        transition_action(action, "published", db)

    action.destination_url = "https://acmedental.example.com/emergency"
    db.commit()
    published = transition_action(action, "published", db)

    assert published.published_at is not None


@pytest.mark.parametrize("target", ["verified", "no_change"])
def test_transition_to_verification_outcome_requires_result_and_sets_timestamp(db, target):
    from app.services.outcome_action_service import (
        OutcomeActionValidationError,
        create_action,
        transition_action,
    )

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)
    action.status = "waiting_verification"
    db.commit()

    with pytest.raises(OutcomeActionValidationError, match="verification_result"):
        transition_action(action, target, db)

    action.verification_result = "verification_scan:2026-08-16"
    db.commit()
    transitioned = transition_action(action, target, db)

    assert transitioned.verified_at is not None
