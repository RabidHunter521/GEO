# backend/app/services/scan_service.py
import time
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.core.config import settings
from app.models.scan import Scan
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.services.gemini_client import GeminiClient
from app.services.brand_detection import detect_brand_mention
from app.services.position_extraction import extract_position
from app.services.query_builder import build_client_queries, build_competitor_queries
from app.services.scoring_service import compute_ai_citability, compute_geo_score

logger = structlog.get_logger()

_INTER_QUERY_DELAY_SECONDS = 0.5  # rate-limit buffer for Gemini free tier
_RANKED_CATEGORIES = ("recommendation", "local")


def run_scan(scan_id: uuid.UUID, db: Session) -> None:
    scan: Scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        logger.error("scan_not_found", scan_id=str(scan_id))
        return

    scan.status = "running"
    db.commit()
    logger.info("scan_started", scan_id=str(scan_id))

    try:
        client: Client = db.query(Client).filter(Client.id == scan.client_id).first()
        competitors: list[Competitor] = (
            db.query(Competitor).filter(Competitor.client_id == scan.client_id).all()
        )
        gemini = GeminiClient(api_key=settings.GEMINI_API_KEY)

        # Run client queries
        client_queries = build_client_queries(client, competitors)
        for q in client_queries:
            response_text = gemini.query(q["query_text"])
            detected = detect_brand_mention(response_text, client.name)

            # Recommendation Position — only for ranked-list categories where the brand appears.
            # Isolated so an extraction failure leaves position None and never fails the scan.
            position = None
            if detected and q["category"] in _RANKED_CATEGORIES:
                try:
                    position = extract_position(response_text, client.name)
                except Exception as exc:
                    logger.error(
                        "position_extraction_failed",
                        scan_id=str(scan_id),
                        query=q["query_text"],
                        error=str(exc),
                    )

            result = ScanQueryResult(
                scan_id=scan.id,
                competitor_id=None,
                category=q["category"],
                query_text=q["query_text"],
                response_text=response_text,
                brand_detected=detected,
                recommendation_position=position,
            )
            db.add(result)
            time.sleep(_INTER_QUERY_DELAY_SECONDS)

        # Run competitor queries
        for competitor in competitors:
            comp_queries = build_competitor_queries(client, competitor)
            for q in comp_queries:
                response_text = gemini.query(q["query_text"])
                detected = detect_brand_mention(response_text, competitor.name)
                result = ScanQueryResult(
                    scan_id=scan.id,
                    competitor_id=competitor.id,
                    category=q["category"],
                    query_text=q["query_text"],
                    response_text=response_text,
                    brand_detected=detected,
                )
                db.add(result)
                time.sleep(_INTER_QUERY_DELAY_SECONDS)

        db.commit()

        # Compute and persist GEO score
        all_results = (
            db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scan.id).all()
        )
        ai_citability = compute_ai_citability(all_results)
        overall = compute_geo_score(client, ai_citability)

        prev_geo_score = (
            db.query(GeoScore)
            .filter(GeoScore.client_id == client.id)
            .order_by(GeoScore.computed_at.desc())
            .first()
        )

        geo_score = GeoScore(
            client_id=client.id,
            scan_id=scan.id,
            ai_citability=ai_citability,
            brand_authority=float(client.brand_authority_score),
            content_quality=float(client.content_quality_score),
            technical_foundations=100.0 if client.technical_foundations_verified else 0.0,
            structured_data=100.0 if client.structured_data_verified else 0.0,
            overall_score=overall,
        )
        db.add(geo_score)

        db.add(ActivityLog(
            client_id=client.id,
            event_type="scan_completed",
            note=f"Scan completed. AI Citability: {ai_citability:.1f}. Overall GEO score: {overall:.1f}.",
        ))

        scan.status = "completed"
        scan.completed_at = datetime.utcnow()
        db.commit()
        logger.info("scan_completed", scan_id=str(scan_id), overall_score=overall)

        # Alert checks — failures must not corrupt scan state
        try:
            from app.services.alert_service import check_score_drop_alert
            check_score_drop_alert(client, geo_score, prev_geo_score, db)
        except Exception as exc:
            logger.error("score_drop_alert_failed", scan_id=str(scan_id), error=str(exc))

        try:
            from app.services.alert_service import check_competitor_overtake_alert
            check_competitor_overtake_alert(client, scan.id, db)
        except Exception as exc:
            logger.error("competitor_overtake_alert_failed", scan_id=str(scan_id), error=str(exc))

        # Action Center refresh — failure must not corrupt scan state
        try:
            from app.services.action_center_service import refresh_actions_for_client
            refresh_actions_for_client(client, geo_score, db)
        except Exception as exc:
            logger.error("action_center_refresh_failed", scan_id=str(scan_id), error=str(exc))

    except Exception as exc:
        # The session may hold a failed transaction — reset it so the
        # status update below can actually commit.
        db.rollback()
        scan.status = "failed"
        db.add(ActivityLog(
            client_id=scan.client_id,
            event_type="scan_failed",
            note=f"Scan failed: {str(exc)[:200]}",
        ))
        db.commit()
        logger.error("scan_failed", scan_id=str(scan_id), error=str(exc))
