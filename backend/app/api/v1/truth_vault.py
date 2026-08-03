"""Authenticated administrative routes for the versioned Truth Vault."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.truth_fact import TruthFact, TruthFactVersion
from app.schemas.truth_fact import (
    TruthFactApprove,
    TruthFactCreate,
    TruthFactListResponse,
    TruthFactOut,
    TruthFactRetire,
    TruthFactVersionDraft,
    TruthFactVersionOut,
)
from app.services import truth_vault_service
from app.services.truth_vault_service import TruthVaultLocationNotFound, TruthVaultValidationError


router = APIRouter(tags=["truth-vault"])


def _get_active_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _get_fact_or_404(client_id: uuid.UUID, fact_id: uuid.UUID, db: Session) -> TruthFact:
    fact = truth_vault_service.get_fact(client_id, fact_id, db)
    if fact is None:
        raise HTTPException(status_code=404, detail="Truth fact not found")
    return fact


def _fact_out(fact: TruthFact, versions: list[TruthFactVersion]) -> TruthFactOut:
    return TruthFactOut(
        id=fact.id,
        client_id=fact.client_id,
        location_id=fact.location_id,
        fact_type=fact.fact_type,
        fact_key=fact.fact_key,
        created_at=fact.created_at,
        versions=[TruthFactVersionOut.model_validate(version) for version in versions],
    )


@router.get(
    "/clients/{client_id}/truth-facts",
    response_model=TruthFactListResponse,
    dependencies=[Depends(require_api_key)],
)
def list_truth_facts(
    client_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    mode: Literal["current", "history"] = "current",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    try:
        facts, total = truth_vault_service.list_facts(
            client_id,
            db,
            location_id=location_id,
            mode=mode,
            page=page,
            page_size=page_size,
        )
    except TruthVaultLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    return TruthFactListResponse(facts=[_fact_out(fact, versions) for fact, versions in facts], total=total)


@router.post(
    "/clients/{client_id}/truth-facts",
    response_model=TruthFactOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_truth_fact(
    client_id: uuid.UUID, body: TruthFactCreate, db: Session = Depends(get_db)
):
    _get_active_client_or_404(client_id, db)
    try:
        fact = truth_vault_service.create_fact(client_id, body, db)
    except TruthVaultLocationNotFound as exc:
        raise HTTPException(status_code=404, detail="Location not found") from exc
    return _fact_out(fact, [])


@router.get(
    "/clients/{client_id}/truth-facts/{fact_id}",
    response_model=TruthFactOut,
    dependencies=[Depends(require_api_key)],
)
def get_truth_fact(client_id: uuid.UUID, fact_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_active_client_or_404(client_id, db)
    fact = _get_fact_or_404(client_id, fact_id, db)
    return _fact_out(fact, truth_vault_service.fact_versions(fact, db))


@router.post(
    "/clients/{client_id}/truth-facts/{fact_id}/versions",
    response_model=TruthFactVersionOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def draft_truth_fact_version(
    client_id: uuid.UUID,
    fact_id: uuid.UUID,
    body: TruthFactVersionDraft,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    return truth_vault_service.draft_version(_get_fact_or_404(client_id, fact_id, db), body, db)


@router.post(
    "/clients/{client_id}/truth-facts/{fact_id}/approve/{version_id}",
    response_model=TruthFactVersionOut,
    dependencies=[Depends(require_api_key)],
)
def approve_truth_fact_version(
    client_id: uuid.UUID,
    fact_id: uuid.UUID,
    version_id: uuid.UUID,
    body: TruthFactApprove,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    _get_fact_or_404(client_id, fact_id, db)
    try:
        return truth_vault_service.approve_version(fact_id, version_id, body.approved_by, db)
    except TruthVaultValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/clients/{client_id}/truth-facts/{fact_id}/retire",
    response_model=TruthFactVersionOut,
    dependencies=[Depends(require_api_key)],
)
def retire_truth_fact(
    client_id: uuid.UUID,
    fact_id: uuid.UUID,
    body: TruthFactRetire,
    db: Session = Depends(get_db),
):
    _get_active_client_or_404(client_id, db)
    _get_fact_or_404(client_id, fact_id, db)
    try:
        return truth_vault_service.retire_fact(fact_id, body.effective_at, db)
    except TruthVaultValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
