# backend/workers/tasks/scan_tasks.py
import uuid
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.scan_service import run_scan

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.scan_tasks.execute_scan", bind=True)
def execute_scan(self, scan_id: str) -> dict:
    logger.info("execute_scan_task_started", scan_id=scan_id)
    db = SessionLocal()
    try:
        run_scan(uuid.UUID(scan_id), db)
        return {"status": "completed", "scan_id": scan_id}
    finally:
        db.close()
