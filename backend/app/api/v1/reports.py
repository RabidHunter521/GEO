import re
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.report import Report
from app.schemas.report import ReportResponse
from app.services.r2_service import presigned_pdf_url
from app.services.worker_health import workers_online
from app.core.time import utcnow

logger = structlog.get_logger()

router = APIRouter(prefix="/clients/{client_id}/reports", tags=["reports"])


@router.get(
    "/scorecard",
    dependencies=[Depends(require_api_key)],
)
def download_scorecard(client_id: uuid.UUID, db: Session = Depends(get_db)):
    """On-demand one-page AI Visibility Scorecard PDF — the shareable snapshot.
    Generated fresh from the latest scan; never persisted."""
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    from app.services.report_service import generate_scorecard_pdf
    pdf_bytes = generate_scorecard_pdf(client_id, db)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=404,
            detail="No scan data available to build a scorecard for this client.",
        )
    slug = re.sub(r"[^A-Za-z0-9]+", "-", c.name).strip("-") or "client"
    filename = f"SeenBy-Scorecard-{slug}-{utcnow():%Y%m%d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/generate",
    dependencies=[Depends(require_api_key)],
)
def generate_report(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")

    # Enqueueing is not the same as running. With the worker stopped, .delay()
    # succeeds against a live Redis and the job waits forever while the UI
    # promises an auto-update that never arrives — walkthrough §6.1 bug 6.
    if not workers_online():
        raise HTTPException(
            status_code=503,
            detail=(
                "The background worker is offline, so the report cannot be built. "
                "Start the Celery worker and try again."
            ),
        )

    from workers.tasks.report_tasks import generate_client_report
    try:
        task = generate_client_report.delay(str(client_id))
    except Exception as exc:
        # The ping passed but the broker refused the publish — report it as the
        # failure it is rather than returning "queued" for a lost job.
        logger.warning("report_enqueue_failed", client_id=str(client_id), error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="Could not reach the job queue, so the report was not started. Try again.",
        ) from exc
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
    reports = (
        db.query(Report)
        .filter(Report.client_id == client_id)
        .order_by(desc(Report.generated_at))
        .all()
    )
    # Expose a freshly signed download URL rather than the stored permanent
    # public link, so access expires once the bucket is private.
    return [
        ReportResponse(
            id=r.id,
            client_id=r.client_id,
            r2_url=presigned_pdf_url(r.r2_key),
            period_start=r.period_start,
            period_end=r.period_end,
            overall_score=r.overall_score,
            generated_at=r.generated_at,
            sent_at=r.sent_at,
        )
        for r in reports
    ]


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
