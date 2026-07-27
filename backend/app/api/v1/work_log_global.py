"""Cross-client work-log reads (spec §3.3).

READ ONLY by design. Publish/dismiss go through
PATCH /clients/{client_id}/work-log/{entry_id}, which already verifies the entry
belongs to the client in the URL. Adding a second write path here would mean a
second copy of that check, free to drift from the first.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.schemas.work_log import WorkLogSuggestionOut
from app.services import work_log_service

router = APIRouter(prefix="/work-log", tags=["work-log-global"])


@router.get(
    "/suggested",
    response_model=list[WorkLogSuggestionOut],
    dependencies=[Depends(require_api_key)],
)
def list_suggested(db: Session = Depends(get_db)):
    out: list[WorkLogSuggestionOut] = []
    for entry, client in work_log_service.suggested_across_clients(db):
        data = WorkLogSuggestionOut.model_validate(entry)
        data.category_label = work_log_service.category_label(entry)
        data.client_name = client.name
        out.append(data)
    return out


@router.get("/suggested/count", dependencies=[Depends(require_api_key)])
def count_suggested(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"count": work_log_service.suggested_count(db)}
