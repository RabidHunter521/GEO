import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.content_roadmap import ContentRoadmap
from app.schemas.content_roadmap import ContentRoadmapResponse

router = APIRouter(prefix="/clients/{client_id}/content-roadmap", tags=["content-roadmap"])


@router.get(
    "",
    response_model=ContentRoadmapResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ContentRoadmap)
        .filter(ContentRoadmap.client_id == client_id)
        .order_by(ContentRoadmap.generated_at.desc())
        .first()
    )


@router.post(
    "/generate",
    response_model=ContentRoadmapResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def generate(client_id: uuid.UUID, db: Session = Depends(get_db)):
    from workers.tasks.content_tasks import run_content_roadmap

    _get_client_or_404(client_id, db)

    roadmap = ContentRoadmap(client_id=client_id, status="pending")
    db.add(roadmap)
    db.commit()
    db.refresh(roadmap)

    run_content_roadmap.delay(str(client_id), str(roadmap.id))
    return roadmap


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
