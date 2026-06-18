# backend/workers/tasks/digest_tasks.py
import uuid
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.services.digest_service import send_client_digest

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.digest_tasks.send_all_weekly_digests")
def send_all_weekly_digests() -> dict:
    """Celery Beat task — runs every Monday 9am UTC."""
    logger.info("send_all_weekly_digests_started")
    db = SessionLocal()
    try:
        clients = (
            db.query(Client)
            .filter(
                Client.archived_at.is_(None),
                Client.is_prospect.is_(False),
                Client.contact_email.isnot(None),
            )
            .all()
        )
        sent = 0
        skipped = 0
        for client in clients:
            try:
                if send_client_digest(client.id, db):
                    sent += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(
                    "digest_failed_for_client",
                    client_id=str(client.id),
                    error=str(exc),
                )
                skipped += 1
        logger.info("send_all_weekly_digests_done", sent=sent, skipped=skipped)
        return {"sent": sent, "skipped": skipped}
    finally:
        db.close()


@celery_app.task(name="workers.tasks.digest_tasks.send_single_client_digest")
def send_single_client_digest(client_id: str) -> dict:
    """Manual trigger task for one client — dispatched by the admin trigger endpoint."""
    logger.info("send_single_client_digest_started", client_id=client_id)
    db = SessionLocal()
    try:
        was_sent = send_client_digest(uuid.UUID(client_id), db)
        return {"sent": was_sent, "client_id": client_id}
    finally:
        db.close()
