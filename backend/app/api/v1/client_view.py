"""Read-only client view API — unauthenticated, gated by a 256-bit share token.

The token in the URL is the credential. Invalid, revoked, and archived all
return a uniform 404 so responses never reveal which state applies. Every
endpoint is read-only and serializes through the client_view whitelist
schemas; raw AI responses and internal fields never reach this surface.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.constants import PLATFORM_LABELS
from app.core.database import get_db
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.report import Report
from app.models.action_recommendation import ActionRecommendation
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.toolkit_files import ToolkitFiles
from app.models.content_roadmap import ContentRoadmap
from app.models.content_analysis import ContentAnalysis
from app.models.activity_log import ActivityLog
from app.schemas.client_view import (
    ClientViewBenchmark,
    ClientViewCompetitorTrends,
    ClientViewPlatform,
    ClientViewProfile,
    ClientViewScore,
    ClientViewTrendSeries,
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
    ClientViewIssueGroup,
    ClientViewToolkit,
    ClientViewRoadmap,
    ClientViewRoadmapItem,
    ClientViewContentGaps,
    ClientViewTopic,
    ClientViewEntity,
    ClientViewSuggestedContent,
    ClientViewActivity,
)
from app.services.benchmark_service import compute_industry_benchmark
from app.services.competitor_intelligence_service import (
    compute_competitor_intelligence,
    compute_competitor_trends,
)
from app.services.issue_detection_service import detect_client_issues

SCORE_HISTORY_LIMIT = 12


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.title())


def _view_platforms(platform_breakdown: dict | None) -> list[ClientViewPlatform]:
    """Whitelist the GeoScore platform breakdown for the client-facing surface."""
    if not platform_breakdown:
        return []
    platforms = []
    for platform, entry in platform_breakdown.items():
        unavailable = entry.get("status") != "ok"
        platforms.append(ClientViewPlatform(
            platform_label=_platform_label(platform),
            seen_by_ai=entry.get("detected", 0) > 0,
            visibility_frequency=None if unavailable else entry.get("visibility", 0.0),
        ))
    return platforms


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

    benchmark = compute_industry_benchmark(client, db)

    latest_report = (
        db.query(Report)
        .filter(Report.client_id == client.id, Report.change_narrative.isnot(None))
        .order_by(desc(Report.generated_at))
        .first()
    )

    # Cheap existence checks so the client view can hide deliverable tabs that
    # have no content yet (a brand-new client never sees an empty tab).
    has_toolkit = (
        db.query(ToolkitFiles.id).filter(ToolkitFiles.client_id == client.id).first() is not None
    )
    has_activity = (
        db.query(ActivityLog.id)
        .filter(
            ActivityLog.client_id == client.id,
            ActivityLog.event_type.in_(list(_CLIENT_ACTIVITY_LABELS.keys())),
        )
        .first()
        is not None
    )
    has_roadmap = (
        db.query(ContentRoadmap.id)
        .filter(ContentRoadmap.client_id == client.id, ContentRoadmap.status == "completed")
        .first()
        is not None
    )
    has_gaps = (
        db.query(ContentAnalysis.id)
        .filter(ContentAnalysis.client_id == client.id, ContentAnalysis.status == "completed")
        .first()
        is not None
    )

    return ClientViewOverview(
        profile=ClientViewProfile(
            name=client.name,
            website=client.website,
            industry=client.industry,
            logo_url=client.logo_url,
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
        platforms=_view_platforms(latest.platform_breakdown) if latest else [],
        benchmark=ClientViewBenchmark(
            industry=benchmark.industry,
            peer_count=benchmark.peer_count,
            industry_average=benchmark.industry_average,
            top_percent=benchmark.top_percent,
        ) if benchmark else None,
        score_history=[
            ClientViewScorePoint(overall_score=s.overall_score, computed_at=s.computed_at)
            for s in reversed(history)  # oldest → newest for charting
        ],
        traffic=[
            ClientViewTrafficPoint(period=t.period, ai_visitors=t.ai_visitors)
            for t in traffic
        ],
        change_narrative=latest_report.change_narrative if latest_report else None,
        change_narrative_period=(
            latest_report.period_start.strftime("%B %Y") if latest_report else None
        ),
        has_our_work=has_toolkit or has_activity,
        has_content_plan=has_roadmap or has_gaps,
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
                platform_label=_platform_label(r.platform),
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
        your_platform_visibility={
            _platform_label(p): v for p, v in intel.client_platform_visibility.items()
        },
        competitors=[
            ClientViewCompetitor(
                name=c.name,
                website=c.website,
                visibility_frequency=c.ai_citability,
                is_winning=c.is_winning,
                platform_visibility={
                    _platform_label(p): v for p, v in c.platform_visibility.items()
                },
                winning_platform_labels=[_platform_label(p) for p in c.winning_platforms],
                queries=[
                    ClientViewCompetitorQuery(
                        platform_label=_platform_label(q.platform),
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


@router.get("/competitors/trends", response_model=ClientViewCompetitorTrends)
def get_competitor_trends(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    trends = compute_competitor_trends(client.id, db)
    return ClientViewCompetitorTrends(
        checked_at=[s.completed_at for s in trends.scans],
        series=[
            ClientViewTrendSeries(name=client.name, is_you=True, points=trends.client.points),
            *[
                ClientViewTrendSeries(name=c.name, is_you=False, points=c.points)
                for c in trends.competitors
            ],
        ],
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


@router.get("/issues", response_model=list[ClientViewIssueGroup])
def get_issues(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    return detect_client_issues(client, db)


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


# Whitelist of activity events the client should see, mapped to a stable UI
# `kind` (icon) and a friendly headline. Events not listed here (alerts,
# hallucination flags, traffic syncs, share-link churn, scan failures, internal
# pre-review report builds) never reach this surface.
_CLIENT_ACTIVITY_LABELS: dict[str, tuple[str, str]] = {
    "scan_completed": ("scan", "AI visibility scan completed"),
    "toolkit_generated": ("toolkit", "AI Readiness files prepared"),
    "toolkit_verified": ("verified", "Site changes verified live"),
    "content_analyzed": ("content", "Content gap analysis completed"),
    "roadmap_generated": ("roadmap", "90-day content plan created"),
    "report_sent": ("report", "Monthly report delivered"),
}

ACTIVITY_LIMIT = 30


@router.get("/toolkit", response_model=ClientViewToolkit | None)
def get_toolkit(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    files = (
        db.query(ToolkitFiles)
        .filter(ToolkitFiles.client_id == client.id)
        .order_by(desc(ToolkitFiles.generated_at))
        .first()
    )
    if not files:
        return None
    return ClientViewToolkit(
        llms_txt=files.llms_txt,
        schema_json=files.schema_json,
        robots_txt=files.robots_txt,
        llms_verified=files.llms_verified,
        schema_verified=files.schema_verified,
        robots_verified=files.robots_verified,
        verified_at=files.verified_at,
        generated_at=files.generated_at,
    )


@router.get("/roadmap", response_model=ClientViewRoadmap | None)
def get_roadmap(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    roadmap = (
        db.query(ContentRoadmap)
        .filter(
            ContentRoadmap.client_id == client.id,
            ContentRoadmap.status == "completed",
        )
        .order_by(desc(ContentRoadmap.generated_at))
        .first()
    )
    if not roadmap:
        return None
    items = [
        ClientViewRoadmapItem(
            month=item.get("month", 1),
            theme=item.get("theme", ""),
            priority=item.get("priority", "medium"),
            content_type=item.get("content_type", ""),
            suggested_title=item.get("suggested_title", ""),
            rationale=item.get("rationale", ""),
            target_queries=item.get("target_queries", []) or [],
            competitors_winning=item.get("competitors_winning", []) or [],
        )
        for item in (roadmap.roadmap_json or [])
    ]
    return ClientViewRoadmap(
        items=items,
        source_query_count=roadmap.source_query_count,
        generated_at=roadmap.generated_at,
    )


@router.get("/content-gaps", response_model=ClientViewContentGaps | None)
def get_content_gaps(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    analysis = (
        db.query(ContentAnalysis)
        .filter(
            ContentAnalysis.client_id == client.id,
            ContentAnalysis.status == "completed",
        )
        .order_by(desc(ContentAnalysis.analyzed_at))
        .first()
    )
    if not analysis:
        return None
    return ClientViewContentGaps(
        topics=[
            ClientViewTopic(topic=t.get("topic", ""), status=t.get("status", "missing"))
            for t in (analysis.topics_json or [])
        ],
        entities=[
            ClientViewEntity(entity=e.get("entity", ""), covered=bool(e.get("covered")))
            for e in (analysis.entities_json or [])
        ],
        suggested_content=[
            ClientViewSuggestedContent(
                topic=s.get("topic", ""),
                title=s.get("title", ""),
                rationale=s.get("rationale", ""),
            )
            for s in (analysis.suggested_content_json or [])
        ],
        quality_recommendation=analysis.content_quality_recommendation,
        analyzed_at=analysis.analyzed_at,
    )


@router.get("/activity", response_model=list[ClientViewActivity])
def get_activity(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.client_id == client.id,
            ActivityLog.event_type.in_(list(_CLIENT_ACTIVITY_LABELS.keys())),
        )
        .order_by(desc(ActivityLog.created_at))
        .limit(ACTIVITY_LIMIT)
        .all()
    )
    out = []
    for r in rows:
        kind, label = _CLIENT_ACTIVITY_LABELS[r.event_type]
        out.append(
            ClientViewActivity(
                kind=kind,
                label=label,
                note=r.note,
                created_at=r.created_at,
            )
        )
    return out
