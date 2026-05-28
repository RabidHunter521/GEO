import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem
from app.schemas.geo_score import GeoScoreResponse

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientListItem], dependencies=[Depends(require_api_key)])
def list_clients(db: Session = Depends(get_db)):
    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None))
        .order_by(desc(Client.created_at))
        .all()
    )
    items = []
    for c in clients:
        latest = (
            db.query(GeoScore)
            .filter(GeoScore.client_id == c.id)
            .order_by(desc(GeoScore.computed_at))
            .first()
        )
        base = ClientResponse.model_validate(c).model_dump()
        items.append(
            ClientListItem(
                **base,
                latest_overall_score=latest.overall_score if latest else None,
                last_scan_at=latest.computed_at if latest else None,
            )
        )
    return items


@router.post(
    "",
    response_model=ClientResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def update_client(client_id: uuid.UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/{client_id}/geo-score/latest",
    response_model=GeoScoreResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_geo_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
