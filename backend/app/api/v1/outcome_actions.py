"""Authenticated, client-scoped Outcome Action endpoints."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.outcome_action import OUTCOME_ACTION_STATUSES, OutcomeAction
from app.schemas.outcome_action import (
    OutcomeActionCreate,
    OutcomeActionListResponse,
    OutcomeActionOut,
    OutcomeActionPatch,
    OutcomeActionStatus,
)
from app.services import outcome_action_service
from app.services.outcome_action_service import (
    InvalidOutcomeTransition,
    OutcomeActionLocationNotFound,
    OutcomeActionValidationError,
)

router = APIRouter(tags=["outcome-actions"])


class OutcomeActionTransition(BaseModel):
    status: OutcomeActionStatus


def _get_active_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _get_action_or_404(client_id: uuid.UUID, action_id: uuid.UUID, db: Session) -> OutcomeAction:
    action = outcome_action_service.get_action(client_id, action_id, db)
    if action is None:
        raise HTTPException(status_code=404, detail="Outcome Action not found")
    return action


def _list_response(query, page: int, page_size: int) -> OutcomeActionListResponse:
    total = query.count()
    actions = query.offset((page - 1) * page_size).limit(page_size).all()
    return OutcomeActionListResponse(
        actions=[OutcomeActionOut.model_validate(action) for action in actions], total=total
    )


@router.get(
    "/clients/{client_id}/outcome-actions",
    response_model=OutcomeActionListResponse,
    dependencies=[Depends(require_api_key)],
)
def list_outcome_actions(
    client_id: uuid.UUID,
    status: str | None = None,
    location_id: uuid.UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    if status is not None and status not in OUTCOME_ACTION_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    query = db.query(OutcomeAction).filter(OutcomeAction.client_id == client_id)
    if status is not None:
        query = query.filter(OutcomeAction.status == status)
    if location_id is not None:
        try:
            outcome_action_service.validate_location_assignment(client_id, location_id, db)
        except OutcomeActionLocationNotFound as exc:
            raise HTTPException(status_code=404, detail="Location not found") from exc
        query = query.filter(OutcomeAction.location_id == location_id)
    if due_from is not None:
        query = query.filter(OutcomeAction.due_date >= due_from)
    if due_to is not None:
        query = query.filter(OutcomeAction.due_date <= due_to)
    return _list_response(query.order_by(OutcomeAction.created_at.desc()), page, page_size)


@router.post(
    "/clients/{client_id}/outcome-actions",
    response_model=OutcomeActionOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_outcome_action(
    client_id: uuid.UUID, body: OutcomeActionCreate, db: Session = Depends(get_db)
):
    _get_active_client_or_404(client_id, db)
    try:
        return outcome_action_service.create_action(client_id, body, db)
    except OutcomeActionLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc


@router.get(
    "/clients/{client_id}/outcome-actions/{action_id}",
    response_model=OutcomeActionOut,
    dependencies=[Depends(require_api_key)],
)
def get_outcome_action(client_id: uuid.UUID, action_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_active_client_or_404(client_id, db)
    return _get_action_or_404(client_id, action_id, db)


@router.patch(
    "/clients/{client_id}/outcome-actions/{action_id}",
    response_model=OutcomeActionOut,
    dependencies=[Depends(require_api_key)],
)
def patch_outcome_action(
    client_id: uuid.UUID,
    action_id: uuid.UUID,
    body: OutcomeActionPatch,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    try:
        return outcome_action_service.patch_action(
            _get_action_or_404(client_id, action_id, db), body, db
        )
    except OutcomeActionLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc


@router.post(
    "/clients/{client_id}/outcome-actions/{action_id}/transition",
    response_model=OutcomeActionOut,
    dependencies=[Depends(require_api_key)],
)
def transition_outcome_action(
    client_id: uuid.UUID,
    action_id: uuid.UUID,
    body: OutcomeActionTransition,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    action = _get_action_or_404(client_id, action_id, db)
    try:
        return outcome_action_service.transition_action(action, body.status, db)
    except (InvalidOutcomeTransition, OutcomeActionValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/outcome-actions/review-queue",
    response_model=OutcomeActionListResponse,
    dependencies=[Depends(require_api_key)],
)
def list_outcome_action_review_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = (
        db.query(OutcomeAction)
        .join(Client, OutcomeAction.client_id == Client.id)
        .filter(Client.archived_at.is_(None), OutcomeAction.status == "recommended")
        .order_by(OutcomeAction.created_at.desc())
    )
    return _list_response(query, page, page_size)
