import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.activity_log import ActivityLog
from app.schemas.activity import ActivityLogEntry

router = APIRouter(prefix="/clients/{client_id}/activity", tags=["activity"])


@router.get(
    "",
    response_model=list[ActivityLogEntry],
    dependencies=[Depends(require_api_key)],
)
def list_activity(
    client_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.client_id == client_id)
        .order_by(desc(ActivityLog.created_at))
        .limit(limit)
        .all()
    )
