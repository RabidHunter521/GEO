"""CRUD and server-side lifecycle validation for Outcome Actions."""
import uuid

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.outcome_action import OutcomeAction
from app.schemas.outcome_action import OutcomeActionCreate, OutcomeActionPatch


ALLOWED_TRANSITIONS = {
    "detected": {"recommended", "dismissed"},
    "recommended": {"approved_internal", "dismissed", "superseded"},
    "approved_internal": {"in_progress", "dismissed"},
    "in_progress": {"waiting_client", "ready_to_publish", "dismissed"},
    "waiting_client": {"in_progress", "ready_to_publish", "dismissed"},
    "ready_to_publish": {"published", "in_progress"},
    "published": {"waiting_verification"},
    "waiting_verification": {"verified", "no_change"},
    "no_change": {"waiting_verification", "superseded"},
}


class InvalidOutcomeTransition(ValueError):
    """Raised when an Outcome Action lifecycle edge is not allowed."""


class OutcomeActionValidationError(ValueError):
    """Raised when a lifecycle transition lacks required supporting evidence."""


def create_action(client_id: uuid.UUID, payload: OutcomeActionCreate, db: Session) -> OutcomeAction:
    """Create one action per client/source reference, preserving specialist records."""
    if payload.source_ref is not None:
        existing = (
            db.query(OutcomeAction)
            .filter(
                OutcomeAction.client_id == client_id,
                OutcomeAction.source_ref == payload.source_ref,
            )
            .first()
        )
        if existing is not None:
            return existing

    action = OutcomeAction(client_id=client_id, **payload.model_dump())
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def list_actions(
    client_id: uuid.UUID, db: Session, status: str | None = None
) -> list[OutcomeAction]:
    query = db.query(OutcomeAction).filter(OutcomeAction.client_id == client_id)
    if status is not None:
        query = query.filter(OutcomeAction.status == status)
    return query.order_by(OutcomeAction.created_at.desc()).all()


def get_action(client_id: uuid.UUID, action_id: uuid.UUID, db: Session) -> OutcomeAction | None:
    return (
        db.query(OutcomeAction)
        .filter(OutcomeAction.client_id == client_id, OutcomeAction.id == action_id)
        .first()
    )


def patch_action(action: OutcomeAction, payload: OutcomeActionPatch, db: Session) -> OutcomeAction:
    """Update reviewed mutable fields without allowing direct status changes."""
    updates = payload.model_dump(exclude_unset=True)
    dismissal_reason = updates.pop("dismissal_reason", None)
    if dismissal_reason is not None:
        action.client_comment = dismissal_reason
    for field, value in updates.items():
        setattr(action, field, value)
    db.commit()
    db.refresh(action)
    return action


def transition_action(action: OutcomeAction, target_status: str, db: Session) -> OutcomeAction:
    """Advance an action through the approved lifecycle and timestamp milestones."""
    if target_status not in ALLOWED_TRANSITIONS.get(action.status, set()):
        raise InvalidOutcomeTransition(
            f"Cannot transition Outcome Action from {action.status} to {target_status}"
        )
    if target_status == "published" and not action.destination_url:
        raise OutcomeActionValidationError("destination_url is required before publication")
    if target_status in {"verified", "no_change"} and not action.verification_result:
        raise OutcomeActionValidationError(
            "verification_result is required before recording a verification outcome"
        )

    now = utcnow()
    action.status = target_status
    action.updated_at = now
    if target_status == "published":
        action.published_at = now
    if target_status in {"verified", "no_change"}:
        action.verified_at = now
    db.commit()
    db.refresh(action)
    return action
