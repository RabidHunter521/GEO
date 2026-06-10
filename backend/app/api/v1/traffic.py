import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.activity_log import ActivityLog
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.schemas.ai_traffic import AiTrafficSnapshotResponse, AiTrafficSnapshotUpsert

router = APIRouter(prefix="/clients/{client_id}/traffic", tags=["ai-traffic"])


@router.get(
    "",
    response_model=list[AiTrafficSnapshotResponse],
    dependencies=[Depends(require_api_key)],
)
def list_traffic(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client_id)
        .order_by(AiTrafficSnapshot.period.desc())
        .limit(12)
        .all()
    )


@router.put(
    "",
    response_model=AiTrafficSnapshotResponse,
    dependencies=[Depends(require_api_key)],
)
def upsert_traffic(client_id: uuid.UUID, body: AiTrafficSnapshotUpsert, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)

    snapshot = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client_id, AiTrafficSnapshot.period == body.period)
        .first()
    )
    if snapshot:
        snapshot.ai_visitors = body.ai_visitors
        snapshot.updated_at = datetime.utcnow()
    else:
        snapshot = AiTrafficSnapshot(
            client_id=client_id,
            period=body.period,
            ai_visitors=body.ai_visitors,
        )
        db.add(snapshot)

    db.add(ActivityLog(
        client_id=client_id,
        event_type="traffic_updated",
        note=f"AI referral traffic for {body.period.strftime('%B %Y')} set to {body.ai_visitors} visitors.",
    ))
    db.commit()
    db.refresh(snapshot)
    return snapshot


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
