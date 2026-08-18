"""Public tokenized client approval endpoints."""
import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit
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

def _approval_headers(response: Response) -> None:
    """Approval links carry a client's business name and pending work — never
    cache them and never let them be indexed. Mirrors the client-view surface."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


# Unauthenticated, token-addressed surface — the only one that had no limiter.
# The 256-bit token makes guessing infeasible, so this is about abuse and load
# (each POST writes a decision + activity row), not brute force. Fails open if
# Redis is down, exactly like the client view.
_approval_rate_limit = rate_limit("action_approvals", max_requests=30, window_seconds=60)

router = APIRouter(
    prefix="/action-approvals",
    tags=["action-approvals"],
    dependencies=[Depends(_approval_headers), Depends(_approval_rate_limit)],
)


def _approval_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Approval link not found")


def _safe_public_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return None
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if address.is_private or address.is_loopback or address.is_link_local:
        return None
    return value


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
        destination_url=_safe_public_url(action.destination_url),
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
