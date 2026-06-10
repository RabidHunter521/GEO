import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.content_analysis import ContentAnalysis
from app.schemas.content_gaps import ContentAnalysisResponse

router = APIRouter(prefix="/clients/{client_id}/content-gaps", tags=["content-gaps"])


@router.get(
    "",
    response_model=ContentAnalysisResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ContentAnalysis)
        .filter(ContentAnalysis.client_id == client_id)
        .order_by(ContentAnalysis.analyzed_at.desc())
        .first()
    )


@router.post(
    "/analyze",
    response_model=ContentAnalysisResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def analyze(client_id: uuid.UUID, db: Session = Depends(get_db)):
    from workers.tasks.content_tasks import run_content_analysis

    _get_client_or_404(client_id, db)

    analysis = ContentAnalysis(client_id=client_id, status="pending")
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    run_content_analysis.delay(str(client_id), str(analysis.id))
    return analysis


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
