import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.core.constants import MAX_COMPETITORS
from app.models.client import Client
from app.models.competitor import Competitor
from app.schemas.competitor import CompetitorCreate, CompetitorResponse

router = APIRouter(prefix="/clients/{client_id}/competitors", tags=["competitors"])


@router.get(
    "",
    response_model=list[CompetitorResponse],
    dependencies=[Depends(require_api_key)],
)
def list_competitors(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return db.query(Competitor).filter(Competitor.client_id == client_id).all()


@router.post(
    "",
    response_model=CompetitorResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def add_competitor(
    client_id: uuid.UUID,
    body: CompetitorCreate,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    count = db.query(Competitor).filter(Competitor.client_id == client_id).count()
    if count >= MAX_COMPETITORS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_COMPETITORS} competitors per client",
        )
    comp = Competitor(client_id=client_id, **body.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.delete(
    "/{competitor_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_competitor(
    client_id: uuid.UUID,
    competitor_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    comp = (
        db.query(Competitor)
        .filter(Competitor.id == competitor_id, Competitor.client_id == client_id)
        .first()
    )
    if comp:
        db.delete(comp)
        db.commit()


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
