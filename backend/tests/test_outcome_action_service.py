"""Outcome Action lifecycle and CRUD service."""
import hashlib
from datetime import date

import pytest
from pydantic import ValidationError


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


def _create_payload(source_ref="content_gap:emergency-dental", **scoring_inputs):
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
        **scoring_inputs,
    )


def _record_approval(action, db):
    from app.schemas.outcome_action import OutcomeActionPatch
    from app.services.outcome_action_service import patch_action

    return patch_action(
        action,
        OutcomeActionPatch(
            approval_decision="approved",
            approval_evidence="reviewed by operations",
        ),
        db,
    )


def _completed_scan(client, db):
    from app.core.time import utcnow
    from app.models.scan import Scan

    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    return scan


def _verification_evidence(scan, basis="visibility_change"):
    return {"scan_id": str(scan.id), "basis": basis}


def test_create_action_and_get_action_are_scoped_to_client(db):
    from app.services.outcome_action_service import create_action, get_action

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")

    action = create_action(client.id, _create_payload(), db)

    assert action.client_id == client.id
    assert action.status == "recommended"
    assert get_action(client.id, action.id, db) == action
    assert get_action(other_client.id, action.id, db) is None


def test_action_location_assignment_and_list_filter_are_limited_to_its_client(db):
    from app.models.business_location import BusinessLocation
    from app.schemas.outcome_action import OutcomeActionPatch
    from app.services.outcome_action_service import (
        OutcomeActionLocationNotFound,
        create_action,
        list_actions,
        patch_action,
    )

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")
    location = BusinessLocation(client_id=client.id, name="Orchard", slug="orchard")
    foreign_location = BusinessLocation(
        client_id=other_client.id, name="Tampines", slug="tampines"
    )
    db.add_all([location, foreign_location])
    db.commit()

    action = create_action(client.id, _create_payload(location_id=location.id), db)

    assert action.location_id == location.id
    assert list_actions(client.id, db, location_id=location.id) == [action]
    with pytest.raises(OutcomeActionLocationNotFound):
        create_action(client.id, _create_payload(location_id=foreign_location.id), db)
    with pytest.raises(OutcomeActionLocationNotFound):
        create_action(client.id, _create_payload("content_gap:foreign", location_id=foreign_location.id), db)
    with pytest.raises(OutcomeActionLocationNotFound):
        patch_action(action, OutcomeActionPatch(location_id=foreign_location.id), db)
    with pytest.raises(OutcomeActionLocationNotFound):
        list_actions(client.id, db, location_id=foreign_location.id)


def test_create_action_reuses_existing_client_source_reference(db):
    from app.services.outcome_action_service import create_action

    client = _make_client(db)

    first = create_action(client.id, _create_payload(), db)
    second = create_action(client.id, _create_payload(), db)

    assert second.id == first.id
    assert db.query(type(first)).count() == 1


def test_create_action_persists_server_owned_priority_score_and_reasons(db):
    from app.services.outcome_action_service import create_action

    client = _make_client(db)
    action = create_action(
        client.id,
        _create_payload(
            commercial_intent=1.0,
            visibility_gap=1.0,
            competitor_advantage=0.8,
            reputation_risk=0.0,
            demand=0.6,
            expected_influence=0.7,
            confidence_score=0.8,
            effort=0.4,
        ),
        db,
    )

    assert action.priority == "medium"
    assert action.priority_score == 58
    assert action.priority_reasons["version"] == "v1"
    assert "high commercial intent" in action.priority_reasons["reasons"]
    assert len(action.priority_reasons["reasons"]) <= 3


def test_patch_action_recalculates_priority_when_scoring_inputs_change(db):
    from app.schemas.outcome_action import OutcomeActionPatch
    from app.services.outcome_action_service import create_action, patch_action

    client = _make_client(db)
    action = create_action(
        client.id,
        _create_payload(
            commercial_intent=1.0,
            visibility_gap=1.0,
            competitor_advantage=0.8,
            reputation_risk=0.0,
            demand=0.6,
            expected_influence=0.7,
            confidence_score=0.8,
            effort=0.4,
        ),
        db,
    )

    patched = patch_action(action, OutcomeActionPatch(reputation_risk=1.0), db)

    assert patched.priority == "high"
    assert patched.priority_score == 76
    assert patched.priority_reasons["inputs"]["reputation_risk"] == 1.0


def test_create_action_requires_source_reference():
    from app.schemas.outcome_action import OutcomeActionCreate

    with pytest.raises(ValidationError, match="source_ref"):
        OutcomeActionCreate(
            source_kind="content_gap",
            source_ref=None,
            title="Publish emergency dental page",
            rationale="High-intent emergency searches are currently won by competitors.",
            action_type="content",
            priority="high",
            confidence="repeated",
        )


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
    with pytest.raises(OutcomeActionValidationError, match="approval"):
        transition_action(action, "published", db)

    _record_approval(action, db)
    published = transition_action(action, "published", db)

    assert published.published_at is not None


def test_recording_approvals_stores_non_unique_evidence_hash_not_token_hash(db):
    from app.services.outcome_action_service import create_action

    client = _make_client(db)
    first = _record_approval(create_action(client.id, _create_payload("content_gap:first"), db), db)
    second = _record_approval(create_action(client.id, _create_payload("content_gap:second"), db), db)

    assert first.client_decision == second.client_decision == "approved"
    assert first.client_decided_at is not None
    assert second.client_decided_at is not None
    expected_hash = hashlib.sha256(b"reviewed by operations").hexdigest()
    assert first.approval_evidence_hash == second.approval_evidence_hash == expected_hash
    assert first.approval_token_hash is None
    assert second.approval_token_hash is None


def test_approval_decision_requires_write_only_evidence():
    from app.schemas.outcome_action import OutcomeActionPatch

    with pytest.raises(ValidationError, match="approval_evidence"):
        OutcomeActionPatch(approval_decision="approved")


def test_patch_action_serializes_uuid_verification_evidence_for_json_storage(db):
    from app.schemas.outcome_action import (
        OutcomeActionPatch,
        OutcomeActionVerificationEvidence,
    )
    from app.services.outcome_action_service import create_action, patch_action

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)
    scan = _completed_scan(client, db)

    patched = patch_action(
        action,
        OutcomeActionPatch(
            verification_result=OutcomeActionVerificationEvidence(
                scan_id=scan.id,
                basis="visibility_change",
            )
        ),
        db,
    )

    assert patched.verification_result == {
        "scan_id": str(scan.id),
        "basis": "visibility_change",
    }


@pytest.mark.parametrize("target, basis", [("verified", "visibility_change"), ("no_change", "no_change")])
def test_transition_to_verification_outcome_requires_scan_backed_evidence_and_approval(
    db, target, basis
):
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

    action.verification_result = {"scan_id": "not-a-uuid", "basis": basis}
    db.commit()
    with pytest.raises(OutcomeActionValidationError, match="scan-backed"):
        transition_action(action, target, db)

    scan = _completed_scan(client, db)
    action.verification_result = _verification_evidence(scan, basis)
    db.commit()
    with pytest.raises(OutcomeActionValidationError, match="approval"):
        transition_action(action, target, db)

    _record_approval(action, db)
    transitioned = transition_action(action, target, db)

    assert transitioned.verified_at is not None
    assert transitioned.scan_id == scan.id


def test_transition_rejects_evidence_from_another_clients_scan(db):
    from app.services.outcome_action_service import (
        OutcomeActionValidationError,
        create_action,
        transition_action,
    )

    client = _make_client(db)
    other_client = _make_client(db, "Other Dental")
    action = create_action(client.id, _create_payload(), db)
    action.status = "waiting_verification"
    action.verification_result = _verification_evidence(_completed_scan(other_client, db))
    db.commit()
    _record_approval(action, db)

    with pytest.raises(OutcomeActionValidationError, match="client"):
        transition_action(action, "verified", db)


def test_transition_rejects_unmatched_query_presence_evidence(db):
    from datetime import timedelta

    from app.core.time import utcnow
    from app.models.scan_query_result import ScanQueryResult
    from app.services.outcome_action_service import (
        OutcomeActionValidationError,
        create_action,
        transition_action,
    )

    client = _make_client(db)
    action = create_action(client.id, _create_payload(source_ref="scan_query_result:not-a-uuid"), db)
    action.status = "waiting_verification"
    action.published_at = utcnow() - timedelta(days=1)
    _record_approval(action, db)
    scan = _completed_scan(client, db)
    db.add(
        ScanQueryResult(
            scan_id=scan.id,
            platform="chatgpt",
            category="recommendation",
            query_text="unrelated query",
            response_text="Acme Dental is visible.",
            brand_detected=True,
        )
    )
    action.verification_result = {
        "basis": "query_presence",
        "before_seen": False,
        "after_seen": True,
        "scan_id": str(scan.id),
        "claim": "Observed after publication; causality not established",
    }
    db.commit()

    with pytest.raises(OutcomeActionValidationError, match="query"):
        transition_action(action, "verified", db)


def test_outcome_action_out_exposes_admin_verification_result(db):
    from app.schemas.outcome_action import OutcomeActionOut
    from app.services.outcome_action_service import create_action

    client = _make_client(db)
    action = create_action(client.id, _create_payload(), db)
    action.verification_result = {"scan_id": "internal", "basis": "visibility_change"}
    db.commit()

    dumped = OutcomeActionOut.model_validate(action).model_dump()
    assert dumped["verification_result"] == {"scan_id": "internal", "basis": "visibility_change"}
    assert "approval_evidence_hash" not in dumped
