import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import (
    WORK_LOG_CATEGORIES,
    WORK_LOG_CATEGORY_LABELS,
    WORK_LOG_STATUSES,
)
from app.core.database import get_db
from app.models.client import Client
from app.models.work_log_entry import WorkLogEntry
from app.schemas.work_log import WorkLogCreateRequest, WorkLogEntryOut, WorkLogPatchRequest
from app.services import work_log_service

router = APIRouter(prefix="/clients/{client_id}/work-log", tags=["work-log"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _out(entry: WorkLogEntry) -> WorkLogEntryOut:
    data = WorkLogEntryOut.model_validate(entry)
    data.category_label = WORK_LOG_CATEGORY_LABELS.get(entry.category, entry.category.title())
    return data


@router.get("", response_model=list[WorkLogEntryOut], dependencies=[Depends(require_api_key)])
def list_work_log(
    client_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    if status is not None and status not in WORK_LOG_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    return [_out(e) for e in work_log_service.list_entries(client_id, db, status=status)]


@router.post("", response_model=WorkLogEntryOut, dependencies=[Depends(require_api_key)])
def create_work_log(
    client_id: uuid.UUID, body: WorkLogCreateRequest, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    if body.category not in WORK_LOG_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")
    if not body.description.strip():
        raise HTTPException(status_code=422, detail="Description is required.")
    entry = work_log_service.create_manual(
        client_id, body.category, body.description, body.entry_date, db
    )
    return _out(entry)


@router.patch("/{entry_id}", response_model=WorkLogEntryOut, dependencies=[Depends(require_api_key)])
def patch_work_log(
    client_id: uuid.UUID, entry_id: uuid.UUID, body: WorkLogPatchRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    entry = db.get(WorkLogEntry, entry_id)
    if not entry or entry.client_id != client_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    patch = body.model_dump(exclude_unset=True)
    if "category" in patch and patch["category"] not in WORK_LOG_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")
    if "status" in patch and patch["status"] not in WORK_LOG_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    return _out(work_log_service.update_entry(entry, patch, db))
