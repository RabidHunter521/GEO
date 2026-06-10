import uuid
from datetime import datetime
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.content_analysis import ContentAnalysis
from app.models.activity_log import ActivityLog
from app.services.content_analysis_service import analyze_content

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.content_tasks.run_content_analysis")
def run_content_analysis(client_id: str, analysis_id: str) -> dict:
    logger.info("run_content_analysis_started", client_id=client_id, analysis_id=analysis_id)
    db = SessionLocal()
    try:
        analysis = db.query(ContentAnalysis).filter(ContentAnalysis.id == uuid.UUID(analysis_id)).first()
        if not analysis:
            logger.error("content_analysis_not_found", analysis_id=analysis_id)
            return {"status": "not_found", "analysis_id": analysis_id}

        analysis.status = "running"
        db.commit()

        try:
            client = db.query(Client).filter(Client.id == uuid.UUID(client_id)).first()
            payload = analyze_content(client)

            analysis.topics_json = payload["topics_json"]
            analysis.entities_json = payload["entities_json"]
            analysis.suggested_content_json = payload.get("suggested_content_json", [])
            analysis.entity_coverage_score = payload["entity_coverage_score"]
            analysis.content_metrics_json = payload["content_metrics_json"]
            analysis.content_quality_recommendation = payload["content_quality_recommendation"]
            analysis.pages_crawled = payload["pages_crawled"]
            analysis.analyzed_at = datetime.utcnow()
            analysis.status = "completed"

            db.add(ActivityLog(
                client_id=client.id,
                event_type="content_analyzed",
                note=(
                    f"Content analysis run. {payload['pages_crawled']} pages analysed. "
                    f"Entity coverage: {payload['entity_coverage_score']:.0f}%."
                ),
            ))
            db.commit()
            logger.info("run_content_analysis_completed", client_id=client_id, analysis_id=analysis_id)
            return {"status": "completed", "analysis_id": analysis_id}
        except Exception as exc:
            analysis.status = "failed"
            db.commit()
            logger.error("run_content_analysis_failed", client_id=client_id, analysis_id=analysis_id, error=str(exc))
            return {"status": "failed", "analysis_id": analysis_id}
    finally:
        db.close()
