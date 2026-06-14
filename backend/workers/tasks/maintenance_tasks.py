# backend/workers/tasks/maintenance_tasks.py
import structlog

from app.core.database import SessionLocal
from app.services.retention_service import delete_churned_clients, purge_raw_responses
from workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.maintenance_tasks.run_data_retention")
def run_data_retention() -> dict:
    """Celery Beat task — daily data-retention housekeeping (CLAUDE.md §8).

    Purges raw scan responses past the 90-day window and hard-deletes clients
    archived past the churn window. Each step is independent: a failure in one
    is logged and does not block the other.
    """
    logger.info("run_data_retention_started")
    db = SessionLocal()
    try:
        try:
            purged = purge_raw_responses(db)
        except Exception as exc:
            db.rollback()
            purged = 0
            logger.error("raw_response_purge_failed", error=str(exc))

        try:
            deleted = delete_churned_clients(db)
        except Exception as exc:
            db.rollback()
            deleted = 0
            logger.error("churned_client_delete_failed", error=str(exc))

        logger.info("run_data_retention_done", purged=purged, deleted=deleted)
        return {"raw_responses_purged": purged, "churned_clients_deleted": deleted}
    finally:
        db.close()
