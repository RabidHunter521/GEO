import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.action_recommendation import ActionRecommendation
from app.schemas.action_recommendation import ActionRecommendationResponse, ActionStatusUpdate
from app.core.time import utcnow

router = APIRouter(prefix="/clients/{client_id}/actions", tags=["action-center"])

_VALID_STATUSES = ("done", "dismissed")


@router.get(
    "",
    response_model=list[ActionRecommendationResponse],
    dependencies=[Depends(require_api_key)],
)
def list_actions(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ActionRecommendation)
        .filter(ActionRecommendation.client_id == client_id, ActionRecommendation.status == "open")
        .order_by(ActionRecommendation.estimated_impact.desc())
        .all()
    )


@router.patch(
    "/{action_id}",
    response_model=ActionRecommendationResponse,
    dependencies=[Depends(require_api_key)],
)
def update_action_status(
    client_id: uuid.UUID,
    action_id: uuid.UUID,
    body: ActionStatusUpdate,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_VALID_STATUSES}")

    action = (
        db.query(ActionRecommendation)
        .filter(ActionRecommendation.id == action_id, ActionRecommendation.client_id == client_id)
        .first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    action.status = body.status
    action.resolved_at = utcnow()
    db.commit()
    db.refresh(action)
    return action


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
