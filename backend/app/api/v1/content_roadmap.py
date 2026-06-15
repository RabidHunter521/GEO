import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.content_roadmap import ContentRoadmap
from app.schemas.content_roadmap import ContentRoadmapResponse
from app.services.content_roadmap_service import generate_article_content

logger = structlog.get_logger()

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


@router.post(
    "/{roadmap_id}/items/{item_index}/content",
    response_model=ContentRoadmapResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_item_content(
    client_id: uuid.UUID,
    roadmap_id: uuid.UUID,
    item_index: int,
    db: Session = Depends(get_db),
):
    """Generate (and cache) the full article draft for one roadmap item.

    Synchronous — one Claude call. Idempotent: if the item already has content,
    it's returned unchanged rather than regenerated."""
    client = _get_client_or_404(client_id, db)

    roadmap = db.get(ContentRoadmap, roadmap_id)
    if not roadmap or roadmap.client_id != client_id:
        raise HTTPException(status_code=404, detail="Roadmap not found")

    items = roadmap.roadmap_json or []
    if item_index < 0 or item_index >= len(items):
        raise HTTPException(status_code=404, detail="Roadmap item not found")

    item = items[item_index]
    if not item.get("article_content"):
        try:
            item["article_content"] = generate_article_content(client, item)
        except Exception:
            logger.exception(
                "roadmap_article_generation_failed",
                client_id=str(client_id),
                roadmap_id=str(roadmap_id),
                item_index=item_index,
            )
            raise HTTPException(status_code=502, detail="Article generation failed")
        items[item_index] = item
        flag_modified(roadmap, "roadmap_json")
        db.commit()
        db.refresh(roadmap)

    return roadmap


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
