import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.remediation_item import RemediationItem
from app.schemas.remediation import RemediationItemResponse, RemediationStatusUpdate
from app.services.remediation_service import (
    get_remediation_items,
    set_remediation_status,
    sync_remediation_items,
)

router = APIRouter(prefix="/clients/{client_id}/remediation", tags=["remediation"])


def _require_client(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.get(
    "",
    response_model=list[RemediationItemResponse],
    dependencies=[Depends(require_api_key)],
)
def list_remediation(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _require_client(client_id, db)
    return get_remediation_items(client_id, db)


@router.post(
    "/sync",
    response_model=list[RemediationItemResponse],
    dependencies=[Depends(require_api_key)],
)
def sync_remediation(client_id: uuid.UUID, db: Session = Depends(get_db)):
    """Reconcile items with the latest scan (newly flagged / auto-corrected),
    then return the refreshed list. Useful after an admin flags a hallucination."""
    _require_client(client_id, db)
    sync_remediation_items(client_id, db)
    return get_remediation_items(client_id, db)


@router.patch(
    "/{item_id}",
    response_model=RemediationItemResponse,
    dependencies=[Depends(require_api_key)],
)
def update_remediation_status(
    client_id: uuid.UUID,
    item_id: uuid.UUID,
    body: RemediationStatusUpdate,
    db: Session = Depends(get_db),
):
    _require_client(client_id, db)
    item = db.get(RemediationItem, item_id)
    if not item or item.client_id != client_id:
        raise HTTPException(status_code=404, detail="Remediation item not found")
    set_remediation_status(item_id, body.status, db)
    db.refresh(item)
    return item
