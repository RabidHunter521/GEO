import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
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
    if not clients:
        return []

    client_ids = [c.id for c in clients]

    # Single query: latest geo score per client using a subquery
    latest_scan_subq = (
        db.query(
            GeoScore.client_id,
            func.max(GeoScore.computed_at).label("max_computed_at"),
        )
        .filter(GeoScore.client_id.in_(client_ids))
        .group_by(GeoScore.client_id)
        .subquery()
    )
    latest_scores = (
        db.query(GeoScore)
        .join(
            latest_scan_subq,
            (GeoScore.client_id == latest_scan_subq.c.client_id)
            & (GeoScore.computed_at == latest_scan_subq.c.max_computed_at),
        )
        .all()
    )
    score_by_client = {s.client_id: s for s in latest_scores}

    items = []
    for c in clients:
        latest = score_by_client.get(c.id)
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
    db.add(ActivityLog(
        client_id=c.id,
        event_type="client_created",
        note=f"Client '{c.name}' added to SeenBy.",
    ))
    db.commit()
    return c


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def update_client(client_id: uuid.UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.delete(
    "/{client_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def archive_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    c.archived_at = datetime.now(timezone.utc)
    db.commit()


@router.get(
    "/{client_id}/geo-score/latest",
    response_model=GeoScoreResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_geo_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
