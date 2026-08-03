"""Authenticated CRUD endpoints for client-owned business locations."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.schemas.business_location import (
    BusinessLocationCreate,
    BusinessLocationDeactivate,
    BusinessLocationOut,
    BusinessLocationPatch,
)
from app.services import business_location_service
from app.services.business_location_service import BusinessLocationValidationError


router = APIRouter(tags=["locations"])


def _get_active_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _get_location_or_404(client_id: uuid.UUID, location_id: uuid.UUID, db: Session):
    location = business_location_service.get_location(client_id, location_id, db)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.get(
    "/clients/{client_id}/locations",
    response_model=list[BusinessLocationOut],
    dependencies=[Depends(require_api_key)],
)
def list_client_locations(
    client_id: uuid.UUID,
    active: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    return business_location_service.list_locations(client_id, db, active=active)


@router.post(
    "/clients/{client_id}/locations",
    response_model=BusinessLocationOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_client_location(
    client_id: uuid.UUID, body: BusinessLocationCreate, db: Session = Depends(get_db)
):
    _get_active_client_or_404(client_id, db)
    return business_location_service.create_location(client_id, body, db)


@router.get(
    "/clients/{client_id}/locations/{location_id}",
    response_model=BusinessLocationOut,
    dependencies=[Depends(require_api_key)],
)
def get_client_location(client_id: uuid.UUID, location_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_active_client_or_404(client_id, db)
    return _get_location_or_404(client_id, location_id, db)


@router.patch(
    "/clients/{client_id}/locations/{location_id}",
    response_model=BusinessLocationOut,
    dependencies=[Depends(require_api_key)],
)
def patch_client_location(
    client_id: uuid.UUID,
    location_id: uuid.UUID,
    body: BusinessLocationPatch,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    return business_location_service.patch_location(
        _get_location_or_404(client_id, location_id, db), body, db
    )


@router.delete(
    "/clients/{client_id}/locations/{location_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def deactivate_client_location(
    client_id: uuid.UUID,
    location_id: uuid.UUID,
    body: BusinessLocationDeactivate | None = None,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    try:
        business_location_service.deactivate_location(
            _get_location_or_404(client_id, location_id, db),
            db,
            replacement_location_id=body.replacement_location_id if body else None,
        )
    except BusinessLocationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)
