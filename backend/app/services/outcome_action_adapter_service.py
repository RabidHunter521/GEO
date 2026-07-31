"""Idempotent adapters from specialist evidence to Outcome Actions."""
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.action_recommendation import ActionRecommendation
from app.models.authority_asset import AuthorityAsset
from app.models.content_deliverable import ContentDeliverable
from app.models.outcome_action import OutcomeAction
from app.models.remediation_item import RemediationItem
from app.services.authority_service import _INTERNAL_ONLY_ASSET_KEYS
from app.services.language_sanitizer import sanitize_text


_RECOMMENDATION_TYPES = {
    "ai_citability": "content",
    "brand_authority": "authority",
    "content_quality": "content",
    "technical_foundations": "technical",
    "structured_data": "structured_data",
}


def suggest_once(
    *,
    client_id: uuid.UUID,
    source_kind: str,
    source_ref: str,
    action_type: str,
    title: str,
    rationale: str,
    priority: str,
    db: Session,
) -> OutcomeAction:
    """Add one recommended action for a source reference in the active transaction."""
    existing = (
        db.query(OutcomeAction)
        .filter(OutcomeAction.client_id == client_id, OutcomeAction.source_ref == source_ref)
        .first()
    )
    if existing is not None:
        return existing

    action = OutcomeAction(
        client_id=client_id,
        source_kind=source_kind,
        source_ref=source_ref,
        action_type=action_type,
        title=sanitize_text(title),
        rationale=sanitize_text(rationale),
        priority=priority,
        confidence="source_record",
        status="recommended",
    )
    try:
        with db.begin_nested():
            db.add(action)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(OutcomeAction)
            .filter(OutcomeAction.client_id == client_id, OutcomeAction.source_ref == source_ref)
            .first()
        )
        if existing is not None:
            return existing
        raise
    return action


def suggest_from_recommendation(recommendation: ActionRecommendation, db: Session) -> OutcomeAction:
    return suggest_once(
        client_id=recommendation.client_id,
        source_kind="recommendation",
        source_ref=f"recommendation:{recommendation.id}",
        action_type=_RECOMMENDATION_TYPES.get(recommendation.dimension, "content"),
        title=recommendation.action_text,
        rationale=f"Recommended from {recommendation.dimension.replace('_', ' ')} assessment.",
        priority=recommendation.priority,
        db=db,
    )


def suggest_from_remediation(item: RemediationItem, db: Session) -> OutcomeAction:
    action_type = "fact_correction" if item.item_type == "hallucination" else "content"
    rationale = item.detail or f"Remediation item identified on {item.platform}."
    return suggest_once(
        client_id=item.client_id,
        source_kind="remediation",
        source_ref=f"remediation:{item.id}",
        action_type=action_type,
        title=f"Resolve: {item.label}",
        rationale=rationale,
        priority="high" if item.item_type == "hallucination" else "medium",
        db=db,
    )


def suggest_from_authority(asset: AuthorityAsset, db: Session) -> OutcomeAction | None:
    if asset.asset_key in _INTERNAL_ONLY_ASSET_KEYS:
        return None
    return suggest_once(
        client_id=asset.client_id,
        source_kind="authority",
        source_ref=f"authority:{asset.id}",
        action_type="authority",
        title=f"Maintain {asset.name}",
        rationale=f"Authority asset is currently {asset.status.replace('_', ' ')}.",
        priority="medium",
        db=db,
    )


def link_deliverable(deliverable: ContentDeliverable, db: Session) -> OutcomeAction:
    action = suggest_once(
        client_id=deliverable.client_id,
        source_kind="deliverable",
        source_ref=f"deliverable:{deliverable.id}",
        action_type="content",
        title=deliverable.title,
        rationale="Content deliverable is available for internal review.",
        priority="medium",
        db=db,
    )
    if action.content_deliverable_id != deliverable.id:
        action.content_deliverable_id = deliverable.id
        db.flush()
    return action
