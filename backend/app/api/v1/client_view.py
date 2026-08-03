from app.core.time import utcnow
"""Read-only client view API — unauthenticated, gated by a 256-bit share token.

The token in the URL is the credential. Invalid, revoked, and archived all
return a uniform 404 so responses never reveal which state applies. Every
endpoint is read-only and serializes through the client_view whitelist
schemas; raw AI responses and internal fields never reach this surface.
"""
import ipaddress
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.constants import (
    PLATFORM_LABELS,
    CLIENT_VIEW_STALE_AFTER_DAYS,
    REMEDIATION_STATUS_LABELS,
)
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.client import Client
from app.models.competitor import Competitor
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
from app.models.outcome_action import OutcomeAction
from app.models.remediation_item import RemediationItem
from app.schemas.client_view import (
    ClientViewBenchmark,
    ClientViewCausalTrend,
    ClientViewCommitment,
    ClientViewCompetitorTrends,
    ClientViewPlatform,
    ClientViewProfile,
    ClientViewProofCard,
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
    ClientViewHeadlineBattle,
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
    ClientViewTrafficValue,
    ClientViewProgressItem,
    ClientViewWorkLogItem,
    ClientViewActionPlanItem,
    ClientViewCompletedWorkItem,
)
from app.services.assessment_service import latest_assessment
from app.services.client_period_summary_service import build_client_period_summary
from app.services.benchmark_service import compute_industry_benchmark
from app.services.revenue_service import estimate_pipeline, estimate_value_at_risk
from app.services.remediation_service import get_remediation_items
from app.services.competitor_intelligence_service import (
    compute_competitor_intelligence,
    compute_competitor_trends,
    competitor_takeaway,
)
from app.services.issue_detection_service import detect_client_issues
from app.services.proof_card_service import select_proof_cards, result_excerpt
from app.services.causality_service import compute_causal_trend
from app.services.ga4_traffic_service import format_breakdown
from app.services.guarantee_service import get_client_commitment
from app.services.headline_battle_service import select_headline_battle
from app.services.r2_service import presigned_pdf_url

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


# Client-facing label for each remediation kind (never the internal item_type).
_REMEDIATION_TYPE_LABELS: dict[str, str] = {
    "hallucination": "Inaccurate AI answer",
    "content_gap": "Competitor winning",
}

_ACTION_STATUS_LABELS: dict[str, str] = {
    "detected": "Detected",
    "recommended": "Recommended",
    "approved_internal": "Approved",
    "in_progress": "In progress",
    "waiting_client": "Waiting for approval",
    "ready_to_publish": "Ready to publish",
    "published": "Published",
    "waiting_verification": "Checking results",
    "verified": "Verified",
    "no_change": "No verified change",
}

_PUBLIC_ACTION_PLAN_STATUSES = {
    "approved_internal",
    "in_progress",
    "waiting_client",
    "ready_to_publish",
    "published",
    "waiting_verification",
}


def _client_proof_cards(client: Client, db: Session) -> list[ClientViewProofCard]:
    """Verbatim win/loss proof cards from the latest completed scan's
    client-owned results. Always [] for a prospect.

    Shared by the /overview `proof_cards` field and the period summary
    builder (client_period_summary_service.build_client_period_summary) so
    the two can never quote a different scan or a different card set on a
    tie — computed once per request, not re-derived (Task 4 review, I4).
    """
    if client.is_prospect:
        return []
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .first()
    )
    if not latest_scan:
        return []
    scan_results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(False),
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )
    competitor_names = [
        c.name
        for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    return [
        ClientViewProofCard(
            kind=pc.kind,
            platform_label=_platform_label(pc.platform),
            category=pc.category,
            excerpt=pc.excerpt,
        )
        for pc in select_proof_cards(scan_results, client.name, competitor_names)
    ]


def _accepted_bullets(db: Session, client_id, dimension: str) -> list[str]:
    """Return evidence_bullets from the latest assessment only when it has been
    accepted or adjusted by an admin. Returns [] otherwise.
    raw_narrative is never returned — only the structured bullet list.
    """
    row = latest_assessment(client_id, dimension, db)
    if row is not None and row.status in ("accepted", "adjusted"):
        return list(row.evidence_bullets)
    return []


def _safe_public_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return None
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if address.is_private or address.is_loopback or address.is_link_local:
        return None
    return value


def _month_label(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%B %Y")


def _verification_claim(action: OutcomeAction) -> str | None:
    result = action.verification_result if isinstance(action.verification_result, dict) else {}
    claim = result.get("claim")
    return claim if isinstance(claim, str) and claim.strip() else None


def require_share_client(
    token: str = Path(...),
    db: Session = Depends(get_db),
) -> Client:
    # Length is validated here (not via Path min/max) so an out-of-range token
    # returns the same uniform 404 as a non-matching one — a 422 would reveal
    # that the token was the "wrong length" vs "valid length, no match".
    if not 20 <= len(token) <= 64:
        raise HTTPException(status_code=404, detail="Not found")
    client = db.query(Client).filter(Client.share_token == token).first()
    if not client or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return client


def require_non_prospect_share_client(
    client: Client = Depends(require_share_client),
) -> Client:
    """Prospects get a deliberately limited view (overview + scan only).
    Every other surface returns the uniform 404 so the link reveals no more."""
    if client.is_prospect:
        raise HTTPException(status_code=404, detail="Not found")
    return client


def _view_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


# Per-IP budget across the whole view surface. A normal page load hits several
# endpoints, so 120/min/IP leaves ample room for real use while throttling abuse
# of a leaked link. Fails open if Redis is down (see rate_limit).
_view_rate_limit = rate_limit("client_view", max_requests=120, window_seconds=60)

# The delivery timeline grows for the life of the account and this endpoint is
# reachable with only a share token, so the response has to be bounded. Newest
# first, so the cap drops the oldest history rather than recent work.
_MAX_PUBLIC_WORK_LOG_ROWS = 200

router = APIRouter(
    prefix="/view/{token}",
    tags=["client-view"],
    dependencies=[Depends(_view_headers), Depends(_view_rate_limit)],
)


@router.get("/overview", response_model=ClientViewOverview)
def get_overview(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    history = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
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
    has_action_plan = (
        db.query(OutcomeAction.id)
        .filter(
            OutcomeAction.client_id == client.id,
            OutcomeAction.status.in_(_PUBLIC_ACTION_PLAN_STATUSES),
        )
        .first()
        is not None
    )

    # Latest-month AI-referral pipeline value (the one money number). traffic is
    # ordered period-ascending, so the last element is the most recent month.
    traffic_value = None
    if traffic:
        latest_traffic = traffic[-1]
        est = estimate_pipeline(latest_traffic.ai_visitors, client)
        # f from the latest score's AI visibility (fraction). latest may be None
        # when no score exists yet — then at-risk is None too.
        vis_f = (latest.ai_citability / 100.0) if latest else None
        at_risk = estimate_value_at_risk(latest_traffic.ai_visitors, vis_f, client)
        traffic_value = ClientViewTrafficValue(
            period=latest_traffic.period,
            ai_visitors=latest_traffic.ai_visitors,
            est_leads=est.est_leads if est else None,
            est_pipeline_rm=est.est_pipeline_rm if est else None,
            est_won_rm=est.est_won_rm if est else None,
            at_risk_leads=at_risk.missed_leads if at_risk else None,
            at_risk_pipeline_rm=at_risk.missed_pipeline_rm if at_risk else None,
            at_risk_won_rm=at_risk.missed_won_rm if at_risk else None,
            breakdown_label=format_breakdown(latest_traffic.breakdown),
        )

    # Freshness — driven by the client's review cadence (a reminder; nothing
    # auto-scans). Stale only flips once the score is older than the threshold.
    last_checked_at = latest.computed_at if latest else None
    next_check_due = None
    is_stale = False
    if last_checked_at:
        next_check_due = (last_checked_at + timedelta(days=client.scan_cadence_days)).date()
        is_stale = (utcnow() - last_checked_at).days >= CLIENT_VIEW_STALE_AFTER_DAYS

    # Same allowlist as /progress below — an item type the client can't see on
    # the Progress tab must not light up the overview either (spec 8 §4).
    has_progress = (
        db.query(RemediationItem.id)
        .filter(
            RemediationItem.client_id == client.id,
            RemediationItem.item_type.in_(_REMEDIATION_TYPE_LABELS.keys()),
        )
        .first()
        is not None
    )

    from app.services import work_log_service
    _since_date = (utcnow() - timedelta(days=30)).date()
    improvements_last_30d = work_log_service.published_count_since(client.id, db, _since_date)
    has_work_log = work_log_service.has_published(client.id, db)
    has_verified_work = (
        db.query(OutcomeAction.id)
        .filter(OutcomeAction.client_id == client.id, OutcomeAction.status == "verified")
        .first()
        is not None
    )

    # Proof of work: how many tracked issues we've corrected this calendar month.
    month_start = utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    fixed_this_month = (
        db.query(RemediationItem)
        .filter(
            RemediationItem.client_id == client.id,
            RemediationItem.status == "corrected",
            RemediationItem.resolved_at >= month_start,
            RemediationItem.item_type.in_(_REMEDIATION_TYPE_LABELS.keys()),
        )
        .count()
    )

    # Verbatim proof cards (non-prospects only) — built from the latest completed
    # scan's client-owned results. Compute-on-read; response_text stays server-side.
    # Shared with build_client_period_summary below (see _client_proof_cards).
    proof_cards = _client_proof_cards(client, db)

    # Visibility commitment — collapsed client-safe state, or hidden.
    commitment = None
    if not client.is_prospect:
        cc = get_client_commitment(client.id, db)
        if cc is not None:
            commitment = ClientViewCommitment(
                metric_label=cc.metric_label,
                baseline=cc.baseline,
                target=cc.target,
                current=cc.current,
                deadline=cc.deadline,
                state=cc.state,
            )

    # Causal proof chart — only meaningful once two scans carry benchmark data.
    causal_trend = None
    if not client.is_prospect:
        trend = compute_causal_trend(client.id, db)
        control_points = [p for p in trend.points if p.control_frequency is not None]
        if len(control_points) >= 2:
            causal_trend = ClientViewCausalTrend(
                dates=[p.completed_at for p in trend.points],
                optimized=[p.optimized_frequency for p in trend.points],
                left_alone=[p.control_frequency for p in trend.points],
            )

    return ClientViewOverview(
        profile=ClientViewProfile(
            name=client.name,
            website=client.website,
            industry=client.industry,
            logo_url=client.logo_url,
            is_prospect=client.is_prospect,
        ),
        latest_score=ClientViewScore(
            overall_score=latest.overall_score,
            ai_visibility=latest.ai_citability,
            brand_authority=latest.brand_authority,
            content_quality=latest.content_quality,
            technical_foundations=latest.technical_foundations,
            structured_data=latest.structured_data,
            computed_at=latest.computed_at,
            brand_authority_evidence=_accepted_bullets(db, client.id, "brand_authority"),
            content_quality_evidence=_accepted_bullets(db, client.id, "content_quality"),
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
        # period_end (the month the report was generated for) matches the PDF's
        # own period label, which is derived from the same end-of-window date —
        # keeps the client view and the PDF showing the same month (#23).
        change_narrative_period=(
            latest_report.period_end.strftime("%B %Y") if latest_report else None
        ),
        has_our_work=has_toolkit or has_activity,
        has_content_plan=has_roadmap or has_gaps or has_action_plan,
        traffic_value=traffic_value,
        has_progress=has_progress,
        has_work_log=has_work_log or has_verified_work,
        improvements_last_30d=improvements_last_30d,
        fixed_this_month=fixed_this_month,
        proof_cards=proof_cards,
        last_checked_at=last_checked_at,
        next_check_due=next_check_due,
        is_stale=is_stale,
        causal_trend=causal_trend,
        commitment=commitment,
        period_summary=build_client_period_summary(client, db, history, proof_cards),
    )


@router.get("/progress", response_model=list[ClientViewProgressItem])
def get_progress(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    """The remediation loop, client-safe: tracked hallucinations and competitor-won
    queries with their Flagged -> In progress -> Corrected status. Proof of the
    work behind the retainer."""
    # Allowlist by type, not "everything stored": misinformation items are
    # spawned by the compliance workflow, whose only client surface is the
    # monthly PDF until Premium gating exists (spec 8 §4). A new item_type must
    # be added to _REMEDIATION_TYPE_LABELS deliberately before clients see it.
    items = [
        i for i in get_remediation_items(client.id, db, include_corrected=True)
        if i.item_type in _REMEDIATION_TYPE_LABELS
    ]
    return [
        ClientViewProgressItem(
            item_type=i.item_type,
            type_label=_REMEDIATION_TYPE_LABELS[i.item_type],
            platform_label=_platform_label(i.platform) if i.platform else None,
            label=i.label,
            detail=i.detail,
            status=i.status,
            status_label=REMEDIATION_STATUS_LABELS.get(i.status, i.status.title()),
        )
        for i in items
    ]


@router.get("/work-log", response_model=list[ClientViewWorkLogItem])
def get_work_log(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    """Published work-log entries — the client-safe delivery timeline.

    Status is filtered in the service query, so a `suggested` or `dismissed`
    row can never reach a client even if the schema changed (spec §3.5).

    Bounded: this is an unauthenticated share-link endpoint, and the timeline
    grows for the life of the account. Newest first, so the cap only ever drops
    the oldest history.
    """
    from app.core.constants import WORK_LOG_CATEGORY_LABELS
    from app.services import work_log_service
    return [
        ClientViewWorkLogItem(
            description=e.description,
            category=e.category,
            category_label=WORK_LOG_CATEGORY_LABELS.get(e.category, e.category.title()),
            entry_date=e.entry_date,
        )
        for e in work_log_service.published_entries(
            client.id, db, limit=_MAX_PUBLIC_WORK_LOG_ROWS
        )
    ]


@router.get("/action-plan", response_model=list[ClientViewActionPlanItem])
def get_action_plan(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    actions = (
        db.query(OutcomeAction)
        .filter(
            OutcomeAction.client_id == client.id,
            OutcomeAction.status.in_(_PUBLIC_ACTION_PLAN_STATUSES),
        )
        .order_by(OutcomeAction.due_date.is_(None), OutcomeAction.due_date, desc(OutcomeAction.created_at))
        .all()
    )
    return [
        ClientViewActionPlanItem(
            title=action.title,
            status_label=_ACTION_STATUS_LABELS.get(
                action.status, action.status.replace("_", " ").title()
            ),
            due_month=_month_label(action.due_date),
            client_safe_summary=action.client_safe_summary,
            destination_url=_safe_public_url(action.destination_url),
        )
        for action in actions
    ]


@router.get("/completed-work", response_model=list[ClientViewCompletedWorkItem])
def get_completed_work(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    actions = (
        db.query(OutcomeAction)
        .filter(OutcomeAction.client_id == client.id, OutcomeAction.status == "verified")
        .order_by(desc(OutcomeAction.verified_at), desc(OutcomeAction.updated_at))
        .all()
    )
    return [
        ClientViewCompletedWorkItem(
            title=action.title,
            status_label=_ACTION_STATUS_LABELS.get(action.status, "Verified"),
            due_month=_month_label(action.due_date),
            completed_month=_month_label(action.verified_at),
            client_safe_summary=action.client_safe_summary,
            destination_url=_safe_public_url(action.destination_url),
            verification_claim=_verification_claim(action),
        )
        for action in actions
    ]


@router.get("/scan", response_model=ClientViewScan)
def get_scan(
    client: Client = Depends(require_share_client),
    db: Session = Depends(get_db),
):
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .first()
    )
    if not latest_scan:
        return ClientViewScan(completed_at=None, results=[])

    # Client's own queries only; flagged answers are known-bad and never shown.
    # Control (benchmark) rows stay off this list — the causal chart is their
    # only client-facing surface.
    results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(False),
            ScanQueryResult.is_control.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .all()
    )
    competitor_names = (
        [c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()]
        if not client.is_prospect
        else []
    )
    view_results = []
    for r in results:
        kind, excerpt = (
            result_excerpt(r, client.name, competitor_names)
            if not client.is_prospect
            else (None, None)
        )
        view_results.append(
            ClientViewScanResult(
                platform_label=_platform_label(r.platform),
                category=r.category,
                query_text=r.query_text,
                seen_by_ai=r.brand_detected,
                ai_search_ranking=r.recommendation_position,
                excerpt=excerpt,
                excerpt_kind=kind,
            )
        )
    return ClientViewScan(completed_at=latest_scan.completed_at, results=view_results)


@router.get("/competitors", response_model=ClientViewCompetitors)
def get_competitors(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    intel = compute_competitor_intelligence(client.id, db)
    battle = select_headline_battle(client.id, db)
    headline_battle = (
        ClientViewHeadlineBattle(
            rival_name=battle.rival_name,
            query_text=battle.query_text,
            platform_label=battle.platform_label,
            move_title=battle.move_title,
            move_angle=battle.move_angle,
        )
        if battle else None
    )
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
                takeaway=competitor_takeaway(c),
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
        headline_battle=headline_battle,
    )


@router.get("/competitors/trends", response_model=ClientViewCompetitorTrends)
def get_competitor_trends(
    client: Client = Depends(require_non_prospect_share_client),
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
    client: Client = Depends(require_non_prospect_share_client),
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
            # Serve a short-lived signed URL, not the permanent public link, so a
            # forwarded report URL stops working within the hour.
            download_url=presigned_pdf_url(r.r2_key),
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
            week=item.get("week", item.get("month", 1)),
            theme=item.get("theme", ""),
            priority=item.get("priority", "medium"),
            content_type=item.get("content_type", ""),
            suggested_title=item.get("suggested_title", ""),
            rationale=item.get("rationale", ""),
            target_queries=item.get("target_queries", []) or [],
            competitors_winning=item.get("competitors_winning", []) or [],
            article_content=item.get("article_content"),
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
