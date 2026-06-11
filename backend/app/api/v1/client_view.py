"""Read-only client view API — unauthenticated, gated by a 256-bit share token.

The token in the URL is the credential. Invalid, revoked, and archived all
return a uniform 404 so responses never reveal which state applies. Every
endpoint is read-only and serializes through the client_view whitelist
schemas; raw AI responses and internal fields never reach this surface.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.report import Report
from app.models.action_recommendation import ActionRecommendation
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.schemas.client_view import (
    ClientViewProfile,
    ClientViewScore,
    ClientViewScorePoint,
    ClientViewTrafficPoint,
    ClientViewOverview,
    ClientViewScanResult,
    ClientViewScan,
    ClientViewCompetitorQuery,
    ClientViewCompetitor,
    ClientViewCompetitors,
    ClientViewReport,
    ClientViewAction,
)
from app.services.competitor_intelligence_service import compute_competitor_intelligence

SCORE_HISTORY_LIMIT = 12


def require_share_client(
    token: str = Path(min_length=20, max_length=64),
    db: Session = Depends(get_db),
) -> Client:
    client = db.query(Client).filter(Client.share_token == token).first()
    if not client or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return client


def _view_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


router = APIRouter(
    prefix="/view/{token}",
    tags=["client-view"],
    dependencies=[Depends(_view_headers)],
)


@router.get("/overview", response_model=ClientViewOverview)
def get_overview(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    history = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(desc(GeoScore.computed_at))
        .limit(SCORE_HISTORY_LIMIT)
        .all()
    )
    latest = history[0] if history else None

    traffic = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client.id)
        .order_by(AiTrafficSnapshot.period)
        .all()
    )

    return ClientViewOverview(
        profile=ClientViewProfile(
            name=client.name,
            website=client.website,
            industry=client.industry,
        ),
        latest_score=ClientViewScore(
            overall_score=latest.overall_score,
            ai_visibility=latest.ai_citability,
            brand_authority=latest.brand_authority,
            content_quality=latest.content_quality,
            technical_foundations=latest.technical_foundations,
            structured_data=latest.structured_data,
            computed_at=latest.computed_at,
        ) if latest else None,
        score_history=[
            ClientViewScorePoint(overall_score=s.overall_score, computed_at=s.computed_at)
            for s in reversed(history)  # oldest → newest for charting
        ],
        traffic=[
            ClientViewTrafficPoint(period=t.period, ai_visitors=t.ai_visitors)
            for t in traffic
        ],
    )


@router.get("/scan", response_model=ClientViewScan)
def get_scan(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return ClientViewScan(completed_at=None, results=[])

    # Client's own queries only; flagged answers are known-bad and never shown.
    results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .all()
    )
    return ClientViewScan(
        completed_at=latest_scan.completed_at,
        results=[
            ClientViewScanResult(
                category=r.category,
                query_text=r.query_text,
                seen_by_ai=r.brand_detected,
                ai_search_ranking=r.recommendation_position,
            )
            for r in results
        ],
    )


@router.get("/competitors", response_model=ClientViewCompetitors)
def get_competitors(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    intel = compute_competitor_intelligence(client.id, db)
    return ClientViewCompetitors(
        your_visibility_frequency=intel.client_ai_citability,
        competitors=[
            ClientViewCompetitor(
                name=c.name,
                website=c.website,
                visibility_frequency=c.ai_citability,
                is_winning=c.is_winning,
                queries=[
                    ClientViewCompetitorQuery(
                        category=q.category,
                        query_text=q.query_text,
                        seen_by_ai=q.brand_detected,
                    )
                    for q in c.queries
                ],
            )
            for c in intel.competitors
        ],
        last_scan_at=intel.last_scan_at,
    )


@router.get("/reports", response_model=list[ClientViewReport])
def get_reports(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    # Only reports that have actually been delivered to the client.
    reports = (
        db.query(Report)
        .filter(Report.client_id == client.id, Report.sent_at.isnot(None))
        .order_by(desc(Report.period_end))
        .all()
    )
    return [
        ClientViewReport(
            id=r.id,
            period_start=r.period_start,
            period_end=r.period_end,
            overall_score=r.overall_score,
            generated_at=r.generated_at,
            download_url=r.r2_url,
        )
        for r in reports
    ]


@router.get("/actions", response_model=list[ClientViewAction])
def get_actions(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    actions = (
        db.query(ActionRecommendation)
        .filter(
            ActionRecommendation.client_id == client.id,
            ActionRecommendation.status == "open",
        )
        .order_by(desc(ActionRecommendation.estimated_impact))
        .all()
    )
    return [
        ClientViewAction(
            action_text=a.action_text,
            dimension=a.dimension,
            priority=a.priority,
            generated_at=a.generated_at,
        )
        for a in actions
    ]
