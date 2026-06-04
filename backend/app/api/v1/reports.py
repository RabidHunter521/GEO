import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.report import Report
from app.schemas.report import ReportResponse

router = APIRouter(prefix="/clients/{client_id}/reports", tags=["reports"])


@router.post(
    "/generate",
    dependencies=[Depends(require_api_key)],
)
def generate_report(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    from workers.tasks.report_tasks import generate_client_report
    task = generate_client_report.delay(str(client_id))
    return {"task_id": task.id, "client_id": str(client_id), "status": "queued"}


@router.get(
    "",
    response_model=list[ReportResponse],
    dependencies=[Depends(require_api_key)],
)
def list_reports(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(Report)
        .filter(Report.client_id == client_id)
        .order_by(desc(Report.generated_at))
        .all()
    )


@router.post(
    "/{report_id}/send",
    dependencies=[Depends(require_api_key)],
)
def send_report(
    client_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if not report or report.client_id != client_id:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.sent_at is not None:
        raise HTTPException(status_code=409, detail="Report already sent")
    from app.services.report_service import send_report_email
    sent = send_report_email(report_id, db)
    return {"sent": sent, "report_id": str(report_id)}
