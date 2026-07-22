import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import MAX_CONTROL_QUERIES
from app.core.database import get_db
from app.models.client import Client
from app.models.control_query import ControlQuery
from app.schemas.control_query import (
    ControlQueryCreate,
    ControlQueryResponse,
    ControlQueryUpdate,
)

router = APIRouter(prefix="/clients/{client_id}/control-queries", tags=["control-queries"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.get(
    "",
    response_model=list[ControlQueryResponse],
    dependencies=[Depends(require_api_key)],
)
def list_control_queries(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ControlQuery)
        .filter(ControlQuery.client_id == client_id)
        .order_by(ControlQuery.created_at)
        .all()
    )


@router.post(
    "",
    response_model=ControlQueryResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_control_query(
    client_id: uuid.UUID,
    body: ControlQueryCreate,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    active_count = (
        db.query(ControlQuery)
        .filter(ControlQuery.client_id == client_id, ControlQuery.active.is_(True))
        .count()
    )
    if active_count >= MAX_CONTROL_QUERIES:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_CONTROL_QUERIES} benchmark queries per client",
        )
    cq = ControlQuery(client_id=client_id, **body.model_dump())
    db.add(cq)
    db.commit()
    db.refresh(cq)
    return cq


@router.patch(
    "/{control_query_id}",
    response_model=ControlQueryResponse,
    dependencies=[Depends(require_api_key)],
)
def update_control_query(
    client_id: uuid.UUID,
    control_query_id: uuid.UUID,
    body: ControlQueryUpdate,
    db: Session = Depends(get_db),
):
    # Deactivate/reactivate only — never delete: history must stay intact.
    _get_client_or_404(client_id, db)
    cq = (
        db.query(ControlQuery)
        .filter(ControlQuery.id == control_query_id, ControlQuery.client_id == client_id)
        .first()
    )
    if not cq:
        raise HTTPException(status_code=404, detail="Benchmark query not found")
    if body.active and not cq.active:
        active_count = (
            db.query(ControlQuery)
            .filter(ControlQuery.client_id == client_id, ControlQuery.active.is_(True))
            .count()
        )
        if active_count >= MAX_CONTROL_QUERIES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_CONTROL_QUERIES} benchmark queries per client",
            )
    cq.active = body.active
    db.commit()
    db.refresh(cq)
    return cq
