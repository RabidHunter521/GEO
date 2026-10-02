import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.placement_target import PlacementTarget
from app.schemas.placement import (
    PatchDraftRequest,
    PatchPlacementRequest,
    PlacementTargetDetail,
    PlacementTargetOut,
)
from app.services import placement_service

router = APIRouter(prefix="/clients/{client_id}/placements", tags=["placements"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _get_target_or_404(client_id: uuid.UUID, target_id: uuid.UUID, db: Session) -> PlacementTarget:
    _get_client_or_404(client_id, db)
    target = db.get(PlacementTarget, target_id)
    if not target or target.client_id != client_id:
        raise HTTPException(status_code=404, detail="Placement target not found")
    return target


@router.get("", response_model=list[PlacementTargetOut], dependencies=[Depends(require_api_key)])
def list_targets(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return placement_service.list_targets(client_id, db)


@router.get("/{target_id}", response_model=PlacementTargetDetail, dependencies=[Depends(require_api_key)])
def get_target(client_id: uuid.UUID, target_id: uuid.UUID, db: Session = Depends(get_db)):
    target = _get_target_or_404(client_id, target_id, db)
    return placement_service.target_detail(target, db)


@router.post(
    "/{target_id}/analyze", response_model=PlacementTargetDetail, dependencies=[Depends(require_api_key)]
)
def analyze_target(client_id: uuid.UUID, target_id: uuid.UUID, db: Session = Depends(get_db)):
    target = _get_target_or_404(client_id, target_id, db)
    placement_service.analyze_target(target, db)
    return placement_service.target_detail(target, db)


@router.patch("/{target_id}", response_model=PlacementTargetDetail, dependencies=[Depends(require_api_key)])
def patch_target(
    client_id: uuid.UUID, target_id: uuid.UUID, body: PatchPlacementRequest, db: Session = Depends(get_db)
):
    target = _get_target_or_404(client_id, target_id, db)
    try:
        placement_service.set_status(target, body.status, db)
    except placement_service.PlacementTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return placement_service.target_detail(target, db)


@router.post(
    "/{target_id}/drafts", response_model=PlacementTargetDetail, dependencies=[Depends(require_api_key)]
)
def create_draft(client_id: uuid.UUID, target_id: uuid.UUID, db: Session = Depends(get_db)):
    target = _get_target_or_404(client_id, target_id, db)
    try:
        draft = placement_service.generate_outreach(target, db)
    except placement_service.PlacementBudgetError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if draft is None:
        raise HTTPException(status_code=502, detail="Draft generation failed. Try again.")
    return placement_service.target_detail(target, db)


@router.patch(
    "/{target_id}/drafts/{draft_id}",
    response_model=PlacementTargetDetail,
    dependencies=[Depends(require_api_key)],
)
def edit_draft(
    client_id: uuid.UUID, target_id: uuid.UUID, draft_id: str, body: PatchDraftRequest,
    db: Session = Depends(get_db),
):
    target = _get_target_or_404(client_id, target_id, db)
    if placement_service.update_draft(target, draft_id, body.subject, body.body, db) is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return placement_service.target_detail(target, db)
