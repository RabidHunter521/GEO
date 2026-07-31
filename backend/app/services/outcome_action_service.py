"""CRUD and server-side lifecycle validation for Outcome Actions."""
import hashlib
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.outcome_action import OutcomeAction
from app.models.scan import Scan
from app.schemas.outcome_action import (
    OutcomeActionCreate,
    OutcomeActionPatch,
    OutcomeActionVerificationEvidence,
    SCORING_INPUT_FIELDS,
)
from app.services.outcome_priority_service import (
    PRIORITY_CALCULATION_VERSION,
    PriorityInputs,
    normalize_priority_inputs,
    score_priority,
)


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
    existing = _get_by_source_ref(client_id, payload.source_ref, db)
    if existing is not None:
        return existing

    action_values = payload.model_dump()
    action_values.update(_priority_fields(_priority_inputs_from_payload(payload)))
    action = OutcomeAction(client_id=client_id, **action_values)
    db.add(action)
    try:
        db.commit()
    except IntegrityError:
        # The database constraint arbitrates concurrent source-event retries.
        db.rollback()
        existing = _get_by_source_ref(client_id, payload.source_ref, db)
        if existing is not None:
            return existing
        raise
    db.refresh(action)
    return action


def _get_by_source_ref(client_id: uuid.UUID, source_ref: str, db: Session) -> OutcomeAction | None:
    return (
        db.query(OutcomeAction)
        .filter(OutcomeAction.client_id == client_id, OutcomeAction.source_ref == source_ref)
        .first()
    )


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
    approval_decision = updates.pop("approval_decision", None)
    approval_evidence = updates.pop("approval_evidence", None)
    changed_scoring_fields = set(payload.model_fields_set).intersection(SCORING_INPUT_FIELDS)
    if payload.verification_result is not None:
        updates["verification_result"] = payload.verification_result.model_dump(mode="json")
    if dismissal_reason is not None:
        action.client_comment = dismissal_reason
    if approval_decision is not None:
        action.client_decision = approval_decision
        action.client_decided_at = utcnow()
        action.approval_evidence_hash = hashlib.sha256(approval_evidence.encode()).hexdigest()
    for field, value in updates.items():
        setattr(action, field, value)
    if changed_scoring_fields:
        action_fields = _priority_fields(
            _priority_inputs_from_payload(payload, _stored_priority_inputs(action))
        )
        for field, value in action_fields.items():
            setattr(action, field, value)
    db.commit()
    db.refresh(action)
    return action


def _priority_inputs_from_payload(
    payload: OutcomeActionCreate | OutcomeActionPatch,
    existing: dict[str, float] | None = None,
) -> PriorityInputs:
    values = existing.copy() if existing else {}
    for field in SCORING_INPUT_FIELDS:
        if isinstance(payload, OutcomeActionPatch) and field not in payload.model_fields_set:
            continue
        values[field] = getattr(payload, field)
    return PriorityInputs(
        commercial_intent=values.get("commercial_intent"),
        visibility_gap=values.get("visibility_gap"),
        competitor_advantage=values.get("competitor_advantage"),
        reputation_risk=values.get("reputation_risk"),
        demand=values.get("demand"),
        expected_influence=values.get("expected_influence"),
        confidence=values.get("confidence_score"),
        effort=values.get("effort"),
    )


def _stored_priority_inputs(action: OutcomeAction) -> dict[str, float]:
    payload = action.priority_reasons
    if not isinstance(payload, dict):
        return {}
    inputs = payload.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def _priority_fields(inputs: PriorityInputs) -> dict[str, object]:
    normalized = normalize_priority_inputs(inputs)
    result = score_priority(normalized)
    stored_inputs = {
        "commercial_intent": normalized.commercial_intent,
        "visibility_gap": normalized.visibility_gap,
        "competitor_advantage": normalized.competitor_advantage,
        "reputation_risk": normalized.reputation_risk,
        "demand": normalized.demand,
        "expected_influence": normalized.expected_influence,
        "confidence_score": normalized.confidence,
        "effort": normalized.effort,
    }
    return {
        "priority": result.band,
        "priority_score": result.score,
        "priority_reasons": {
            "version": PRIORITY_CALCULATION_VERSION,
            "reasons": list(result.reasons),
            "inputs": stored_inputs,
        },
    }


def transition_action(action: OutcomeAction, target_status: str, db: Session) -> OutcomeAction:
    """Advance an action through the approved lifecycle and timestamp milestones."""
    if target_status not in ALLOWED_TRANSITIONS.get(action.status, set()):
        raise InvalidOutcomeTransition(
            f"Cannot transition Outcome Action from {action.status} to {target_status}"
        )
    if target_status == "published" and not action.destination_url:
        raise OutcomeActionValidationError("destination_url is required before publication")
    if target_status in {"verified", "no_change"}:
        _validate_verification_evidence(action, target_status, db)
    if target_status in {"published", "verified", "no_change"}:
        _require_approval(action)

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


def _require_approval(action: OutcomeAction) -> None:
    if not (
        action.client_decision == "approved"
        and action.client_decided_at is not None
        and action.approval_evidence_hash
    ):
        raise OutcomeActionValidationError(
            "recorded approval evidence is required before publication or verification completion"
        )


def _validate_verification_evidence(
    action: OutcomeAction, target_status: str, db: Session
) -> None:
    if not action.verification_result:
        raise OutcomeActionValidationError(
            "verification_result is required before recording a verification outcome"
        )
    try:
        evidence = OutcomeActionVerificationEvidence.model_validate(action.verification_result)
    except ValueError as exc:
        raise OutcomeActionValidationError(
            "verification_result must be scan-backed verification evidence"
        ) from exc
    expected_basis = "visibility_change" if target_status == "verified" else "no_change"
    if evidence.basis != expected_basis:
        raise OutcomeActionValidationError(
            f"verification evidence basis must be {expected_basis} for {target_status}"
        )
    scan = db.get(Scan, evidence.scan_id)
    if scan is None or scan.status != "completed":
        raise OutcomeActionValidationError("verification evidence must reference a completed scan")
    if scan.client_id != action.client_id:
        raise OutcomeActionValidationError("verification evidence scan must belong to the action client")
    if action.scan_id is not None and action.scan_id != scan.id:
        raise OutcomeActionValidationError("verification evidence scan must match the action scan")
    action.scan_id = scan.id
