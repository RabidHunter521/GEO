"""Secure public approval tokens for Outcome Actions."""
import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.client import Client
from app.models.outcome_action import OutcomeAction


DEFAULT_APPROVAL_EXPIRY_DAYS = 14
MAX_CLIENT_COMMENT_LENGTH = 2000


class ApprovalTokenUnavailable(ValueError):
    """Raised when a public approval token cannot be resolved."""


class ApprovalCommentTooLong(ValueError):
    """Raised when a public approval comment exceeds the safe storage limit."""


class InvalidApprovalDecision(ValueError):
    """Raised when a public approval decision is not part of the contract."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_approval_link(
    action: OutcomeAction,
    db: Session,
    *,
    expires_in_days: int = DEFAULT_APPROVAL_EXPIRY_DAYS,
) -> str:
    """Create a one-time public approval token and store only its SHA-256 hash."""
    for _ in range(3):
        token = secrets.token_urlsafe(32)
        action.approval_token_hash = _hash_token(token)
        action.approval_expires_at = utcnow() + timedelta(days=expires_in_days)
        db.add(action)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            db.refresh(action)
            continue
        db.refresh(action)
        return token
    raise RuntimeError("Could not create a unique approval token")


def resolve_approval_token(token: str, db: Session) -> OutcomeAction | None:
    """Return the active action for a public token, or None for every unavailable state."""
    token_hash = _hash_token(token)
    return (
        db.query(OutcomeAction)
        .join(Client, OutcomeAction.client_id == Client.id)
        .filter(
            OutcomeAction.approval_token_hash == token_hash,
            OutcomeAction.approval_expires_at.is_not(None),
            OutcomeAction.approval_expires_at > utcnow(),
            Client.archived_at.is_(None),
        )
        .first()
    )


def record_client_decision(
    token: str,
    decision: str,
    comment: str | None,
    db: Session,
) -> OutcomeAction:
    """Record a single-use client decision without storing raw approval evidence."""
    if decision not in {"approve", "request_changes"}:
        raise InvalidApprovalDecision("decision must be approve or request_changes")
    if comment is not None and len(comment) > MAX_CLIENT_COMMENT_LENGTH:
        raise ApprovalCommentTooLong("comment must be 2,000 characters or fewer")

    token_hash = _hash_token(token)
    action = (
        db.query(OutcomeAction)
        .join(Client, OutcomeAction.client_id == Client.id)
        .filter(
            OutcomeAction.approval_token_hash == token_hash,
            OutcomeAction.approval_expires_at.is_not(None),
            OutcomeAction.approval_expires_at > utcnow(),
            Client.archived_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if action is None:
        raise ApprovalTokenUnavailable("Approval link not found")

    decided_at = utcnow()
    stored_decision = "approved" if decision == "approve" else "request_changes"
    action.client_decision = stored_decision
    action.client_comment = comment
    action.client_decided_at = decided_at
    if decision == "approve":
        evidence = "|".join(
            [
                token_hash,
                str(action.id),
                stored_decision,
                comment or "",
                decided_at.isoformat(),
            ]
        )
        action.approval_evidence_hash = hashlib.sha256(evidence.encode()).hexdigest()
    else:
        action.approval_evidence_hash = None
    action.approval_token_hash = None
    action.approval_expires_at = None
    db.commit()
    db.refresh(action)
    return action
