"""Secure public approval token behavior for Outcome Actions."""
import hashlib
import re
from datetime import timedelta

import pytest


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _make_client(db, name="Acme Dental", archived=False):
    from app.core.time import utcnow
    from app.models.client import Client

    client = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    if archived:
        client.archived_at = utcnow()
    db.add(client)
    db.commit()
    return client


def _make_action(db, client=None, **overrides):
    from app.models.outcome_action import OutcomeAction

    client = client or _make_client(db)
    values = {
        "client_id": client.id,
        "source_kind": "content_gap",
        "source_ref": f"content-gap:{client.id}",
        "title": "Publish emergency dental page",
        "rationale": "Competitors currently win high-intent emergency searches.",
        "action_type": "content",
        "priority": "high",
        "confidence": "repeated",
        "status": "waiting_client",
        "client_safe_summary": "Create an emergency dental page for high-intent searches.",
        "destination_url": "https://acmedental.example.com/emergency",
    }
    values.update(overrides)
    action = OutcomeAction(**values)
    db.add(action)
    db.commit()
    return action


def test_create_approval_link_stores_sha256_hash_without_plaintext_token(db):
    from app.services.action_approval_service import create_approval_link

    action = _make_action(db)

    token = create_approval_link(action, db)

    assert TOKEN_RE.match(token)
    assert action.approval_token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert action.approval_token_hash != token
    assert action.approval_expires_at is not None
    assert token not in repr(action.__dict__)


def test_resolve_approval_token_returns_valid_action_only(db):
    from app.services.action_approval_service import create_approval_link, resolve_approval_token

    action = _make_action(db)
    token = create_approval_link(action, db)

    assert resolve_approval_token(token, db).id == action.id
    assert resolve_approval_token("not-a-real-token", db) is None


def test_resolve_approval_token_rejects_expired_token(db):
    from app.core.time import utcnow
    from app.services.action_approval_service import create_approval_link, resolve_approval_token

    action = _make_action(db)
    token = create_approval_link(action, db)
    action.approval_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    assert resolve_approval_token(token, db) is None


def test_resolve_approval_token_rejects_archived_client(db):
    from app.services.action_approval_service import create_approval_link, resolve_approval_token

    archived = _make_client(db, archived=True)
    action = _make_action(db, client=archived)
    token = create_approval_link(action, db)

    assert resolve_approval_token(token, db) is None


def test_record_approve_is_single_use_and_satisfies_publication_gate(db):
    from app.services.action_approval_service import (
        ApprovalTokenUnavailable,
        create_approval_link,
        record_client_decision,
        resolve_approval_token,
    )
    from app.services.outcome_action_service import transition_action

    action = _make_action(db, status="ready_to_publish")
    token = create_approval_link(action, db)

    decided = record_client_decision(token, "approve", "Looks good.", db)

    assert decided.client_decision == "approved"
    assert decided.client_comment == "Looks good."
    assert decided.client_decided_at is not None
    assert decided.approval_evidence_hash
    assert decided.approval_token_hash is None
    assert decided.approval_expires_at is None
    assert resolve_approval_token(token, db) is None
    with pytest.raises(ApprovalTokenUnavailable):
        record_client_decision(token, "approve", None, db)

    published = transition_action(decided, "published", db)
    assert published.published_at is not None


def test_record_request_changes_keeps_comment_without_approval_evidence(db):
    from app.services.action_approval_service import create_approval_link, record_client_decision
    from app.services.outcome_action_service import OutcomeActionValidationError, transition_action

    action = _make_action(db, status="ready_to_publish")
    token = create_approval_link(action, db)

    decided = record_client_decision(token, "request_changes", "Please soften the claim.", db)

    assert decided.client_decision == "request_changes"
    assert decided.client_comment == "Please soften the claim."
    assert decided.client_decided_at is not None
    assert decided.approval_evidence_hash is None
    assert decided.approval_token_hash is None
    with pytest.raises(OutcomeActionValidationError, match="approval"):
        transition_action(decided, "published", db)


def test_record_client_decision_rejects_comments_over_2000_characters(db):
    from app.services.action_approval_service import (
        ApprovalCommentTooLong,
        create_approval_link,
        record_client_decision,
    )

    action = _make_action(db)
    token = create_approval_link(action, db)

    with pytest.raises(ApprovalCommentTooLong):
        record_client_decision(token, "request_changes", "x" * 2001, db)
