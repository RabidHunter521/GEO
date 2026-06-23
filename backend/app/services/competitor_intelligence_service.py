import uuid

from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.competitor import (
    CompetitorIntelligenceResponse,
    CompetitorScore,
    CompetitorQueryBreakdown,
    CompetitorTrendsResponse,
    TrendScanPoint,
    TrendSeries,
)

TREND_SCAN_LIMIT = 12

# Friendly, client-safe phrasing for each query category in a takeaway sentence.
# High-intent categories (recommendation, local) come first when we pick the
# category to name — that's the "so what" a client cares about most.
_CATEGORY_PHRASES: dict[str, str] = {
    "recommendation": '"best in industry" recommendation questions',
    "local": "local recommendation questions",
    "comparison": "head-to-head comparison questions",
    "brand": "brand-name questions",
}
_CATEGORY_ORDER = ["recommendation", "local", "comparison", "brand"]


def competitor_takeaway(comp: CompetitorScore) -> str | None:
    """A one-line, client-safe 'so what' for a competitor — derived purely from the
    structured scan breakdown (never raw AI responses). Turns the frequency bar
    into a sentence a client can act on. Returns None when there's nothing useful
    to say (no scan data for this competitor).

    Language rules (CLAUDE.md §2): only 'seen by AI' / 'visibility frequency';
    never 'cited', 'mentioned', 'ranking', or 'citation rate'.
    """
    if not comp.queries:
        return None

    seen = [q for q in comp.queries if q.brand_detected]
    total = len(comp.queries)

    if not seen:
        return "Not seen by AI in any question we tracked — you're ahead here."

    # The category where this competitor shows up most (high-intent first on ties).
    counts: dict[str, int] = {}
    for q in seen:
        counts[q.category] = counts.get(q.category, 0) + 1
    top_category = max(
        counts,
        key=lambda c: (counts[c], -_CATEGORY_ORDER.index(c) if c in _CATEGORY_ORDER else -99),
    )
    category_phrase = _CATEGORY_PHRASES.get(top_category, "questions buyers ask AI")

    win_labels = [PLATFORM_LABELS.get(p, p.title()) for p in (comp.winning_platforms or [])]

    if comp.is_winning and win_labels:
        return (
            f"Seen by AI on {len(seen)} of {total} questions and ahead of you on "
            f"{', '.join(win_labels)} — strongest on {category_phrase}."
        )
    if comp.is_winning:
        return (
            f"Seen by AI on {len(seen)} of {total} questions — strongest on "
            f"{category_phrase}, where they're winning buyer attention."
        )
    return (
        f"Seen by AI on {len(seen)} of {total} questions, mostly {category_phrase} — "
        f"but you're ahead overall."
    )


def compute_competitor_intelligence(client_id: uuid.UUID, db: Session) -> CompetitorIntelligenceResponse:
    """Per-competitor visibility breakdown from the latest completed scan.

    Shared by the admin competitors page and the read-only client view.
    Caller is responsible for verifying the client exists / is not archived.
    """
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    if not latest_scan:
        return CompetitorIntelligenceResponse(
            client_ai_citability=None,
            competitors=[
                CompetitorScore(
                    id=c.id,
                    name=c.name,
                    website=c.website,
                    ai_citability=0.0,
                    queries=[],
                    is_winning=False,
                )
                for c in competitors
            ],
            last_scan_at=None,
        )

    all_results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == latest_scan.id)
        .all()
    )

    client_results = [r for r in all_results if r.competitor_id is None]
    client_citability = (
        round(sum(1 for r in client_results if r.brand_detected) / len(client_results) * 100, 1)
        if client_results
        else 0.0
    )
    client_platform_visibility = visibility_by_platform(client_results)

    competitor_scores = []
    for comp in competitors:
        comp_results = [r for r in all_results if r.competitor_id == comp.id]
        comp_citability = (
            round(sum(1 for r in comp_results if r.brand_detected) / len(comp_results) * 100, 1)
            if comp_results
            else 0.0
        )
        comp_platform_visibility = visibility_by_platform(comp_results)
        competitor_scores.append(
            CompetitorScore(
                id=comp.id,
                name=comp.name,
                website=comp.website,
                ai_citability=comp_citability,
                queries=[
                    CompetitorQueryBreakdown(
                        platform=r.platform,
                        category=r.category,
                        query_text=r.query_text,
                        brand_detected=r.brand_detected,
                    )
                    for r in comp_results
                ],
                is_winning=comp_citability > client_citability,
                platform_visibility=comp_platform_visibility,
                winning_platforms=[
                    p
                    for p, visibility in comp_platform_visibility.items()
                    if visibility > client_platform_visibility.get(p, 0.0)
                ],
            )
        )

    return CompetitorIntelligenceResponse(
        client_ai_citability=client_citability,
        client_platform_visibility=client_platform_visibility,
        competitors=competitor_scores,
        last_scan_at=latest_scan.completed_at.isoformat() + "Z" if latest_scan.completed_at else None,
    )


def visibility_by_platform(results: list) -> dict[str, float]:
    """Visibility frequency (% of queries where the brand was seen) per platform.

    Public: also used by alert_service for per-platform overtake detail.
    """
    counts: dict[str, list[int]] = {}
    for r in results:
        detected, total = counts.setdefault(r.platform, [0, 0])
        counts[r.platform] = [detected + (1 if r.brand_detected else 0), total + 1]
    return {
        platform: round(detected / total * 100, 1)
        for platform, (detected, total) in counts.items()
        if total
    }


def compute_competitor_trends(
    client_id: uuid.UUID, db: Session, limit: int = TREND_SCAN_LIMIT
) -> CompetitorTrendsResponse:
    """Visibility frequency per scan for the client and each competitor.

    Computed from persisted brand_detected flags (purge-proof — response_text
    is never needed). A point is None when that competitor has no rows in a
    scan (e.g. added after it ran).
    """
    from app.models.client import Client

    client = db.get(Client, client_id)
    client_name = client.name if client else "You"

    scans = (
        db.query(Scan.id, Scan.completed_at)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .limit(limit)
        .all()
    )
    scans = list(reversed(scans))  # oldest → newest for charting
    scan_ids = [s.id for s in scans]

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    visibility: dict[tuple, float] = {}
    if scan_ids:
        rows = (
            db.query(
                ScanQueryResult.scan_id,
                ScanQueryResult.competitor_id,
                func.count().label("total"),
                func.sum(
                    case((ScanQueryResult.brand_detected.is_(True), 1), else_=0)
                ).label("detected"),
            )
            .filter(ScanQueryResult.scan_id.in_(scan_ids))
            .group_by(ScanQueryResult.scan_id, ScanQueryResult.competitor_id)
            .all()
        )
        visibility = {
            (row.scan_id, row.competitor_id): round(row.detected / row.total * 100, 1)
            for row in rows
            if row.total
        }

    def series_for(competitor_id: uuid.UUID | None) -> list[float | None]:
        return [visibility.get((scan_id, competitor_id)) for scan_id in scan_ids]

    return CompetitorTrendsResponse(
        scans=[TrendScanPoint(scan_id=s.id, completed_at=s.completed_at) for s in scans],
        client=TrendSeries(competitor_id=None, name=client_name, points=series_for(None)),
        competitors=[
            TrendSeries(competitor_id=c.id, name=c.name, points=series_for(c.id))
            for c in competitors
        ],
    )
