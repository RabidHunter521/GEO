"""CRUD and server-side lifecycle validation for Outcome Actions."""
import hashlib
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.content_deliverable import ContentDeliverable
from app.models.geo_score import GeoScore
from app.models.outcome_action import OutcomeAction
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
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
        updates["verification_result"] = payload.verification_result.model_dump(
            mode="json", exclude_none=True
        )
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
    query_presence_matches_target = (
        evidence.basis == "query_presence"
        and evidence.before_seen is False
        and evidence.after_seen == (target_status == "verified")
    )
    if evidence.basis != expected_basis and not query_presence_matches_target:
        raise OutcomeActionValidationError(
            f"verification evidence basis must be {expected_basis} for {target_status}"
        )
    scan = db.get(Scan, evidence.scan_id)
    if scan is None or scan.status != "completed":
        raise OutcomeActionValidationError("verification evidence must reference a completed scan")
    if scan.client_id != action.client_id:
        raise OutcomeActionValidationError("verification evidence scan must belong to the action client")
    if evidence.basis == "query_presence":
        _validate_query_presence_evidence(action, evidence, scan, target_status, db)
    elif action.scan_id is not None and action.scan_id != scan.id:
        raise OutcomeActionValidationError("verification evidence scan must match the action scan")
    action.scan_id = scan.id


def _validate_query_presence_evidence(
    action: OutcomeAction,
    evidence: OutcomeActionVerificationEvidence,
    scan: Scan,
    target_status: str,
    db: Session,
) -> None:
    if action.published_at is None:
        raise OutcomeActionValidationError("query presence verification requires publication")
    if scan.completed_at is None or scan.completed_at <= action.published_at:
        raise OutcomeActionValidationError("query presence verification requires a post-publication scan")
    source_result = source_query_result_for_action(action, db)
    if source_result is None:
        raise OutcomeActionValidationError("query presence verification requires source query evidence")
    source_scan = db.get(Scan, source_result.scan_id)
    if source_scan is None or source_scan.completed_at is None or source_scan.completed_at >= action.published_at:
        raise OutcomeActionValidationError("query presence source scan must predate publication")
    if source_result.brand_detected:
        raise OutcomeActionValidationError("query presence source query must start unseen")
    after_result = matching_query_result(scan.id, source_result, db)
    expected_seen = target_status == "verified"
    if after_result is None or bool(after_result.brand_detected) != expected_seen:
        raise OutcomeActionValidationError("query presence verification requires matching query evidence")


def source_query_result_for_action(action: OutcomeAction, db: Session) -> ScanQueryResult | None:
    """Resolve stable pre-publication query evidence for an Outcome Action."""
    if action.published_at is None:
        return None
    source_ref = action.source_ref or ""
    prefix, _, raw_id = source_ref.partition(":")
    direct = _scan_query_result_by_ref(prefix, raw_id, db)
    if direct is not None:
        return _eligible_source_result(action, direct, db)
    if prefix == "remediation":
        return _source_from_remediation(action, raw_id, db)
    if prefix == "deliverable":
        return _source_from_deliverable(action, raw_id, db)
    if prefix == "recommendation":
        return _source_from_recommendation(action, raw_id, db)
    return None


def _scan_query_result_by_ref(prefix: str, raw_id: str, db: Session) -> ScanQueryResult | None:
    if prefix not in {"scan_query_result", "scan_query_results"} or not raw_id:
        return None
    try:
        result_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    return db.get(ScanQueryResult, result_id)


def _eligible_source_result(
    action: OutcomeAction, result: ScanQueryResult | None, db: Session
) -> ScanQueryResult | None:
    if result is None or result.competitor_id is not None or result.is_control or result.brand_detected:
        return None
    source_scan = db.get(Scan, result.scan_id)
    if (
        source_scan is None
        or source_scan.client_id != action.client_id
        or source_scan.status != "completed"
        or source_scan.completed_at is None
        or action.published_at is None
        or source_scan.completed_at >= action.published_at
    ):
        return None
    return result


def _source_from_remediation(action: OutcomeAction, raw_id: str, db: Session) -> ScanQueryResult | None:
    try:
        item_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    item = db.get(RemediationItem, item_id)
    if item is None or item.client_id != action.client_id or not item.platform or not item.label:
        return None
    return (
        db.query(ScanQueryResult)
        .join(Scan, Scan.id == ScanQueryResult.scan_id)
        .filter(
            Scan.client_id == action.client_id,
            Scan.status == "completed",
            Scan.completed_at < action.published_at,
            ScanQueryResult.platform == item.platform,
            ScanQueryResult.query_text == item.label,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.brand_detected.is_(False),
        )
        .order_by(desc(Scan.completed_at), desc(ScanQueryResult.created_at))
        .first()
    )


def _source_from_deliverable(action: OutcomeAction, raw_id: str, db: Session) -> ScanQueryResult | None:
    try:
        deliverable_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    deliverable = db.get(ContentDeliverable, deliverable_id)
    if deliverable is None or deliverable.client_id != action.client_id:
        return None
    result_ids = deliverable.source_context.get("result_ids", []) if isinstance(deliverable.source_context, dict) else []
    for raw_result_id in result_ids:
        try:
            result = db.get(ScanQueryResult, uuid.UUID(str(raw_result_id)))
        except ValueError:
            continue
        eligible = _eligible_source_result(action, result, db)
        if eligible is not None:
            return eligible
    return None


def _source_from_recommendation(action: OutcomeAction, raw_id: str, db: Session) -> ScanQueryResult | None:
    try:
        recommendation_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    recommendation = db.get(ActionRecommendation, recommendation_id)
    if (
        recommendation is None
        or recommendation.client_id != action.client_id
        or recommendation.geo_score_id is None
        or recommendation.dimension != "ai_citability"
    ):
        return None
    geo_score = db.get(GeoScore, recommendation.geo_score_id)
    if geo_score is None or geo_score.scan_id is None:
        return None
    return (
        db.query(ScanQueryResult)
        .join(Scan, Scan.id == ScanQueryResult.scan_id)
        .filter(
            Scan.id == geo_score.scan_id,
            Scan.client_id == action.client_id,
            Scan.status == "completed",
            Scan.completed_at < action.published_at,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.brand_detected.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .first()
    )


def matching_query_result(
    scan_id: uuid.UUID, source_result: ScanQueryResult, db: Session
) -> ScanQueryResult | None:
    return (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.platform == source_result.platform,
            ScanQueryResult.category == source_result.category,
            ScanQueryResult.query_text == source_result.query_text,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
        )
        .order_by(desc(ScanQueryResult.created_at), desc(ScanQueryResult.id))
        .first()
    )
