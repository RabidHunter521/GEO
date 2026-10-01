import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
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
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    rows = (
        db.query(ActivityLog)
        .filter(ActivityLog.client_id == client_id)
        .order_by(desc(ActivityLog.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        ActivityLogEntry(
            id=entry.id,
            event_type=entry.event_type,
            note=entry.note,
            created_at=entry.created_at,
            actor_name=entry.actor_name,
        )
        for entry in rows
    ]
