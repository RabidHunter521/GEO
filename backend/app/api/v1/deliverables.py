import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_deliverable import ContentDeliverable
from app.schemas.deliverable import DeliverableCreate, DeliverableResponse, DeliverableUpdate
from app.services.deliverable_service import DELIVERABLE_TYPES, generate_deliverable

router = APIRouter(prefix="/clients/{client_id}/deliverables", tags=["deliverables"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _get_deliverable_or_404(
    client_id: uuid.UUID, deliverable_id: uuid.UUID, db: Session
) -> ContentDeliverable:
    d = db.get(ContentDeliverable, deliverable_id)
    if not d or d.client_id != client_id:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return d


@router.post("", response_model=DeliverableResponse, dependencies=[Depends(require_api_key)])
def create(client_id: uuid.UUID, body: DeliverableCreate, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    if body.type not in DELIVERABLE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown deliverable type: {body.type}")
    competitor = None
    if body.type == "comparison_page":
        if body.competitor_id is None:
            raise HTTPException(status_code=422, detail="A comparison page needs a competitor")
        competitor = db.get(Competitor, body.competitor_id)
        if not competitor or competitor.client_id != client_id:
            raise HTTPException(status_code=404, detail="Competitor not found")
    deliverable = generate_deliverable(client, body.type, db, competitor=competitor)
    if deliverable is None:
        raise HTTPException(
            status_code=502, detail="Generation didn't complete — try again."
        )
    return deliverable


@router.get("", response_model=list[DeliverableResponse], dependencies=[Depends(require_api_key)])
def list_deliverables(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ContentDeliverable)
        .filter(ContentDeliverable.client_id == client_id)
        .order_by(ContentDeliverable.generated_at.desc())
        .all()
    )


@router.patch(
    "/{deliverable_id}", response_model=DeliverableResponse,
    dependencies=[Depends(require_api_key)],
)
def update(
    client_id: uuid.UUID, deliverable_id: uuid.UUID,
    body: DeliverableUpdate, db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    d = _get_deliverable_or_404(client_id, deliverable_id, db)
    if body.status is not None and body.status != "reviewed":
        raise HTTPException(status_code=422, detail="Status can only move to reviewed")
    if body.title is not None:
        d.title = body.title[:512]
    if body.body_md is not None:
        d.body_md = body.body_md
    if body.status == "reviewed" and d.status != "reviewed":
        d.status = "reviewed"
        d.reviewed_at = datetime.now(UTC)
        db.add(ActivityLog(
            client_id=client_id,
            event_type="deliverable_reviewed",
            note=f"Content deliverable reviewed: {d.title[:80]}",
        ))
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}/download", dependencies=[Depends(require_api_key)])
def download(client_id: uuid.UUID, deliverable_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    d = _get_deliverable_or_404(client_id, deliverable_id, db)
    filename = f"{d.type}-{d.generated_at:%Y%m%d}.md"
    return Response(
        content=d.body_md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
