import uuid
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.content_analysis import ContentAnalysis
from app.models.content_roadmap import ContentRoadmap
from app.models.activity_log import ActivityLog
from app.services.content_analysis_service import analyze_content
from app.services.content_roadmap_service import generate_roadmap
from app.core.time import utcnow

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
            analysis.analyzed_at = utcnow()
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


@celery_app.task(name="workers.tasks.content_tasks.run_content_roadmap")
def run_content_roadmap(client_id: str, roadmap_id: str) -> dict:
    logger.info("run_content_roadmap_started", client_id=client_id, roadmap_id=roadmap_id)
    db = SessionLocal()
    try:
        roadmap = db.query(ContentRoadmap).filter(ContentRoadmap.id == uuid.UUID(roadmap_id)).first()
        if not roadmap:
            logger.error("content_roadmap_not_found", roadmap_id=roadmap_id)
            return {"status": "not_found", "roadmap_id": roadmap_id}

        roadmap.status = "running"
        db.commit()

        try:
            client = db.query(Client).filter(Client.id == uuid.UUID(client_id)).first()
            payload = generate_roadmap(client, db)

            roadmap.roadmap_json = payload["roadmap_json"]
            roadmap.source_query_count = payload["source_query_count"]
            roadmap.generated_at = utcnow()
            roadmap.status = "completed"

            db.add(ActivityLog(
                client_id=client.id,
                event_type="roadmap_generated",
                note=(
                    f"90-day content roadmap generated from {payload['source_query_count']} "
                    f"lost queries. {len(payload['roadmap_json'])} items planned."
                ),
            ))
            db.commit()
            logger.info("run_content_roadmap_completed", client_id=client_id, roadmap_id=roadmap_id)
            return {"status": "completed", "roadmap_id": roadmap_id}
        except Exception as exc:
            roadmap.status = "failed"
            db.commit()
            logger.error("run_content_roadmap_failed", client_id=client_id, roadmap_id=roadmap_id, error=str(exc))
            return {"status": "failed", "roadmap_id": roadmap_id}
    finally:
        db.close()
