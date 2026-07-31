"""Public tokenized client approval endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.schemas.action_approval import (
    ActionApprovalDecisionIn,
    ActionApprovalDecisionOut,
    ActionApprovalPublic,
)
from app.services.action_approval_service import (
    ApprovalCommentTooLong,
    ApprovalTokenUnavailable,
    InvalidApprovalDecision,
    record_client_decision,
    resolve_approval_token,
)

router = APIRouter(prefix="/action-approvals", tags=["action-approvals"])


def _approval_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Approval link not found")


def _public_payload(token: str, db: Session) -> ActionApprovalPublic:
    action = resolve_approval_token(token, db)
    if action is None:
        raise _approval_not_found()
    client = db.get(Client, action.client_id)
    if client is None or client.archived_at is not None or action.approval_expires_at is None:
        raise _approval_not_found()
    return ActionApprovalPublic(
        business_name=client.name,
        action_title=action.title,
        client_safe_summary=action.client_safe_summary,
        deliverable_url=None,
        destination_url=action.destination_url,
        expires_at=action.approval_expires_at,
    )


@router.get("/{token}", response_model=ActionApprovalPublic)
def get_action_approval(token: str, db: Session = Depends(get_db)):
    return _public_payload(token, db)


@router.post("/{token}", response_model=ActionApprovalDecisionOut)
def post_action_approval(
    token: str,
    body: ActionApprovalDecisionIn,
    db: Session = Depends(get_db),
):
    try:
        action = record_client_decision(token, body.decision, body.comment, db)
    except ApprovalTokenUnavailable as exc:
        raise _approval_not_found() from exc
    except ApprovalCommentTooLong as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvalidApprovalDecision as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    decision = "approved" if action.client_decision == "approved" else "request_changes"
    return ActionApprovalDecisionOut(status="recorded", decision=decision)
