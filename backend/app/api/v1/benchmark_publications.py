"""Authenticated publication workflow for the SEA AI Visibility Index
(Phase 6 Task 7).

Deliberately a different module from `public_benchmarks.py`. The plan named
one file for both, but every route here requires an API key and the one there
is anonymous; keeping them together is how an auth dependency eventually gets
dropped from the wrong route during an edit. One file, one trust level.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.schemas.benchmark_publication import (
    PublicationApprove,
    PublicationCreate,
    PublicationResponse,
    PublicationWithdraw,
)
from app.services import benchmark_publication_service as service

router = APIRouter(
    prefix="/benchmarks/publications",
    tags=["benchmark-publications"],
    dependencies=[Depends(require_api_key)],
)


def _run(action, *args, **kwargs):
    """Map a workflow rule violation onto 409, not 500.

    A rejected approval is a legitimate outcome of the review process, not a
    server fault, and it needs to read that way in the operator's client.
    """
    try:
        return action(*args, **kwargs)
    except service.PublicationError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if detail == "publication not found" else 409, detail=detail)


@router.get("", response_model=list[PublicationResponse])
def list_publications(db: Session = Depends(get_db)):
    return [PublicationResponse.from_model(item) for item in service.list_publications(db)]


@router.post("", response_model=PublicationResponse, status_code=201)
def create_publication(body: PublicationCreate, db: Session = Depends(get_db)):
    publication = _run(
        service.create_publication,
        db,
        slug=body.slug,
        title=body.title,
        edition=body.edition,
        period_start=body.period_start,
        period_end=body.period_end,
        generated_by=body.generated_by,
        methodology_version=body.methodology_version,
    )
    return PublicationResponse.from_model(publication)


@router.post("/{publication_id}/approve", response_model=PublicationResponse)
def approve_publication(
    publication_id: uuid.UUID, body: PublicationApprove, db: Session = Depends(get_db)
):
    publication = _run(service.approve_publication, db, publication_id, body.approved_by)
    return PublicationResponse.from_model(publication)


@router.post("/{publication_id}/publish", response_model=PublicationResponse)
def publish_publication(publication_id: uuid.UUID, db: Session = Depends(get_db)):
    publication = _run(service.publish_publication, db, publication_id)
    return PublicationResponse.from_model(publication)


@router.post("/{publication_id}/withdraw", response_model=PublicationResponse)
def withdraw_publication(
    publication_id: uuid.UUID, body: PublicationWithdraw, db: Session = Depends(get_db)
):
    publication = _run(service.withdraw_publication, db, publication_id, body.reason)
    return PublicationResponse.from_model(publication)
