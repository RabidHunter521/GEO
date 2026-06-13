import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem, ShareTokenResponse
from app.schemas.geo_score import GeoScoreResponse
from app.schemas.benchmark import IndustryBenchmarkResponse
from app.services.benchmark_service import compute_industry_benchmark
from app.services.client_list_service import build_client_list
from app.services.share_link_service import generate_share_token, revoke_share_token

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientListItem], dependencies=[Depends(require_api_key)])
def list_clients(db: Session = Depends(get_db)):
    return build_client_list(db)


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


@router.post(
    "/{client_id}/share-token",
    response_model=ShareTokenResponse,
    dependencies=[Depends(require_api_key)],
)
def create_or_rotate_share_token(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    generate_share_token(c, db)
    return ShareTokenResponse(
        share_token=c.share_token,
        share_token_created_at=c.share_token_created_at,
    )


@router.delete(
    "/{client_id}/share-token",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_share_token(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    revoke_share_token(c, db)


@router.get(
    "/{client_id}/benchmark",
    response_model=IndustryBenchmarkResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_industry_benchmark(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return compute_industry_benchmark(c, db)


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
