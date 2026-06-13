# backend/app/services/scan_service.py
import time
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import structlog

from app.core.constants import ACTIVE_SCAN_STALE_MINUTES, PLATFORM_LABELS, SCAN_PLATFORMS
from app.models.scan import Scan
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.services.platform_clients import get_platform_client
from app.services.brand_detection import detect_brand_mention
from app.services.position_extraction import extract_position
from app.services.query_builder import build_client_queries, build_competitor_queries
from app.services.scoring_service import (
    compute_ai_citability,
    compute_geo_score,
    compute_platform_breakdown,
)

logger = structlog.get_logger()

_INTER_QUERY_DELAY_SECONDS = 0.5  # rate-limit buffer between platform calls
_RANKED_CATEGORIES = ("recommendation", "local")


def has_active_scan(client_id: uuid.UUID, db: Session) -> bool:
    """True if the client has a pending/running scan triggered within the
    stale window. Scans older than the window are assumed dead (crashed
    worker) and don't block new triggers. triggered_at is stored as naive UTC."""
    threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=ACTIVE_SCAN_STALE_MINUTES
    )
    return (
        db.query(Scan.id)
        .filter(
            Scan.client_id == client_id,
            Scan.status.in_(["pending", "running"]),
            Scan.triggered_at >= threshold,
        )
        .first()
        is not None
    )


def _enabled_platforms(client: Client) -> list[str]:
    """Client's enabled platforms in canonical order; legacy/empty values mean all."""
    enabled = client.enabled_platforms or []
    valid = [p for p in SCAN_PLATFORMS if p in enabled]
    return valid or list(SCAN_PLATFORMS)


def _run_platform_queries(
    platform: str,
    scan: Scan,
    client: Client,
    competitors: list[Competitor],
) -> list[ScanQueryResult]:
    """Run all queries for one platform. Raises on platform failure — results
    are returned (not persisted) so a failed platform leaves no partial rows."""
    platform_client = get_platform_client(platform)
    results: list[ScanQueryResult] = []

    for q in build_client_queries(client, competitors):
        response_text = platform_client.query(q["query_text"])
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
                    scan_id=str(scan.id),
                    platform=platform,
                    query=q["query_text"],
                    error=str(exc),
                )

        results.append(ScanQueryResult(
            scan_id=scan.id,
            platform=platform,
            competitor_id=None,
            category=q["category"],
            query_text=q["query_text"],
            response_text=response_text,
            brand_detected=detected,
            recommendation_position=position,
        ))
        time.sleep(_INTER_QUERY_DELAY_SECONDS)

    for competitor in competitors:
        for q in build_competitor_queries(client, competitor):
            response_text = platform_client.query(q["query_text"])
            detected = detect_brand_mention(response_text, competitor.name)
            results.append(ScanQueryResult(
                scan_id=scan.id,
                platform=platform,
                competitor_id=competitor.id,
                category=q["category"],
                query_text=q["query_text"],
                response_text=response_text,
                brand_detected=detected,
            ))
            time.sleep(_INTER_QUERY_DELAY_SECONDS)

    return results


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

        # Per-platform isolation: one provider outage never fails the whole scan.
        failed_platforms: list[str] = []
        for platform in _enabled_platforms(client):
            try:
                platform_results = _run_platform_queries(platform, scan, client, competitors)
            except Exception as exc:
                failed_platforms.append(platform)
                db.add(ActivityLog(
                    client_id=client.id,
                    event_type="scan_platform_unavailable",
                    note=f"{PLATFORM_LABELS.get(platform, platform)} was unavailable this scan: {str(exc)[:150]}",
                ))
                logger.error(
                    "scan_platform_failed",
                    scan_id=str(scan_id),
                    platform=platform,
                    error=str(exc),
                )
                continue
            db.add_all(platform_results)

        db.commit()

        all_results = (
            db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scan.id).all()
        )
        if not all_results:
            raise RuntimeError(
                f"All platforms failed: {', '.join(failed_platforms) or 'none enabled'}"
            )

        # Compute and persist GEO score
        platform_breakdown = compute_platform_breakdown(all_results, failed_platforms)
        ai_citability = compute_ai_citability(all_results, platform_breakdown)
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
            platform_breakdown=platform_breakdown,
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
