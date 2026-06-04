import uuid
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.report import Report
from app.services.report_service import generate_report_pdf

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.report_tasks.generate_client_report")
def generate_client_report(client_id: str) -> dict:
    """Manual trigger — generate PDF report for one client."""
    logger.info("generate_client_report_started", client_id=client_id)
    db = SessionLocal()
    try:
        report = generate_report_pdf(uuid.UUID(client_id), db)
        return {"generated": report is not None, "client_id": client_id}
    finally:
        db.close()


@celery_app.task(name="workers.tasks.report_tasks.check_and_generate_due_reports")
def check_and_generate_due_reports() -> dict:
    """Celery Beat task — runs daily at 9am UTC. Generates reports for clients due today."""
    logger.info("check_and_generate_due_reports_started")
    db = SessionLocal()
    generated = 0
    skipped = 0
    try:
        clients = (
            db.query(Client)
            .filter(
                Client.archived_at.is_(None),
                Client.contact_email.isnot(None),
            )
            .all()
        )
        for client in clients:
            if not _is_report_due(client, db):
                skipped += 1
                continue
            try:
                report = generate_report_pdf(client.id, db)
                if report:
                    generated += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(
                    "report_generation_failed",
                    client_id=str(client.id),
                    error=str(exc),
                )
                skipped += 1
        logger.info("check_and_generate_due_reports_done", generated=generated, skipped=skipped)
        return {"generated": generated, "skipped": skipped}
    finally:
        db.close()


def _is_report_due(client: Client, db: Session) -> bool:
    """Return True if 30 days have passed since signup (or last report)."""
    last_report: Report | None = (
        db.query(Report)
        .filter(Report.client_id == client.id)
        .order_by(Report.generated_at.desc())
        .first()
    )
    reference = last_report.generated_at if last_report else client.created_at
    return datetime.utcnow() >= reference + timedelta(days=30)

