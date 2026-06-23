# backend/workers/tasks/maintenance_tasks.py
import structlog

from app.core.database import SessionLocal
from app.services.retention_service import delete_churned_clients, purge_raw_responses
from app.services.scan_service import reap_stale_scans
from workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.maintenance_tasks.run_stale_scan_reaper")
def run_stale_scan_reaper() -> dict:
    """Celery Beat task — reconcile scans stuck in pending/running past the
    stale window (crashed or timed-out worker) to 'failed'. Runs every 15 min
    so a phantom in-progress scan never lingers on the dashboard for long.
    """
    logger.info("run_stale_scan_reaper_started")
    db = SessionLocal()
    try:
        reaped = reap_stale_scans(db)
        logger.info("run_stale_scan_reaper_done", reaped=reaped)
        return {"stale_scans_reaped": reaped}
    finally:
        db.close()


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
