"""Global dashboard reads — cross-client feed + summary tiles.

READ ONLY by design (spec 2026-08-09): the dashboard links out to the pages
where work happens; it never mutates state.

ADMIN-ONLY: cost aggregation lives here. Never import this module from
client_view code paths — nothing on a share-token surface may reach it.

Timezone contract: activity_log.created_at and geo_scores.computed_at are
naive UTC (see app/core/time.utcnow); llm_call_logs.called_at is the one
timezone-aware column. Period carries naive bounds and derives aware copies
strictly for LlmCallLog comparisons — comparing naive to aware is the bug
this design exists to prevent.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.constants import (
    DEFAULT_EVENT_TIER,
    EVENT_CATEGORIES,
    EVENT_LINK_ROUTES,
    EVENT_TIER_ATTENTION,
    EVENT_TIERS,
)
from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.llm_call_log import LlmCallLog
from app.schemas.dashboard import (
    AttentionCounts,
    CostSummary,
    DashboardFeedItem,
    DashboardFeedResponse,
    DashboardMover,
    DashboardSummaryResponse,
    PortfolioHealth,
    ServiceCost,
)


@dataclass(frozen=True)
class Period:
    """Half-open interval [start, end) in naive UTC."""

    start: datetime
    end: datetime

    @property
    def start_aware(self) -> datetime:
        return self.start.replace(tzinfo=timezone.utc)

    @property
    def end_aware(self) -> datetime:
        return self.end.replace(tzinfo=timezone.utc)


def resolve_period(
    days: int, start_date: date | None, end_date: date | None
) -> Period:
    if start_date is not None and end_date is not None:
        # Whole calendar days, end-exclusive: [start 00:00, end+1day 00:00)
        return Period(
            datetime.combine(start_date, dtime.min),
            datetime.combine(end_date + timedelta(days=1), dtime.min),
        )
    now = utcnow()
    return Period(now - timedelta(days=days), now)


def _tier(event_type: str) -> str:
    return EVENT_TIERS.get(event_type, DEFAULT_EVENT_TIER)


def _link_path(client_id: uuid.UUID, event_type: str) -> str:
    # Unknown types fall back to the per-client activity page, which always
    # exists and shows the raw entry.
    route = EVENT_LINK_ROUTES.get(event_type, "/activity")
    return f"/clients/{client_id}{route}"


def get_feed(
    db: Session,
    period: Period,
    *,
    client_id: uuid.UUID | None = None,
    category: str | None = None,
    event_type: str | None = None,
    attention_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> DashboardFeedResponse:
    q = (
        db.query(ActivityLog, Client.name)
        .join(Client, ActivityLog.client_id == Client.id)
        .filter(Client.archived_at.is_(None))
        .filter(
            ActivityLog.created_at >= period.start,
            ActivityLog.created_at < period.end,
        )
    )
    if client_id is not None:
        q = q.filter(ActivityLog.client_id == client_id)
    if event_type:
        q = q.filter(ActivityLog.event_type == event_type)
    elif category:
        types = [t for t, c in EVENT_CATEGORIES.items() if c == category]
        q = q.filter(ActivityLog.event_type.in_(types))
    if attention_only:
        attention = [
            t for t, tier in EVENT_TIERS.items() if tier == EVENT_TIER_ATTENTION
        ]
        q = q.filter(ActivityLog.event_type.in_(attention))

    total = q.count()
    rows = (
        q.order_by(desc(ActivityLog.created_at)).offset(offset).limit(limit).all()
    )
    items = [
        DashboardFeedItem(
            id=entry.id,
            client_id=entry.client_id,
            client_name=name,
            event_type=entry.event_type,
            note=entry.note,
            created_at=entry.created_at,
            tier=_tier(entry.event_type),
            category=EVENT_CATEGORIES.get(entry.event_type),
            link_path=_link_path(entry.client_id, entry.event_type),
        )
        for entry, name in rows
    ]
    return DashboardFeedResponse(
        items=items, total=total, has_more=offset + len(items) < total
    )


_ATTENTION_FIELD_BY_EVENT = {
    "scan_failed": "scans_failed",
    "scan_platform_unavailable": "platforms_unavailable",
    "hallucination_flagged": "hallucinations_flagged",
    "alert_sent": "alerts_sent",
    "citation_flip": "share_of_source_changes",
}


def get_summary(
    db: Session, period: Period, *, client_id: uuid.UUID | None = None
) -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        attention=_attention_counts(db, period, client_id),
        portfolio=_portfolio_health(db, period, client_id),
        cost=_cost_summary(db, period, client_id),
    )


def _attention_counts(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> AttentionCounts:
    q = (
        db.query(ActivityLog.event_type, func.count(ActivityLog.id))
        .join(Client, ActivityLog.client_id == Client.id)
        .filter(Client.archived_at.is_(None))
        .filter(
            ActivityLog.created_at >= period.start,
            ActivityLog.created_at < period.end,
            ActivityLog.event_type.in_(_ATTENTION_FIELD_BY_EVENT),
        )
        .group_by(ActivityLog.event_type)
    )
    if client_id is not None:
        q = q.filter(ActivityLog.client_id == client_id)
    counts = dict(q.all())
    return AttentionCounts(
        **{
            field: counts.get(event, 0)
            for event, field in _ATTENTION_FIELD_BY_EVENT.items()
        }
    )


def _portfolio_health(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> PortfolioHealth:
    clients_q = db.query(Client).filter(
        Client.archived_at.is_(None), Client.is_prospect.is_(False)
    )
    if client_id is not None:
        clients_q = clients_q.filter(Client.id == client_id)
    clients = clients_q.all()
    name_by_id = {c.id: c.name for c in clients}
    if not clients:
        return PortfolioHealth(
            average_score=None, average_delta=None, clients_scored=0,
            biggest_gainer=None, biggest_decliner=None,
        )

    # One pass over scores, newest first: the first row seen per client is
    # its latest (≤ period end); the first row with computed_at < start is
    # its baseline. Clients with no baseline contribute no delta (spec).
    scores = (
        db.query(GeoScore)
        .filter(
            GeoScore.client_id.in_(name_by_id),
            GeoScore.computed_at < period.end,
        )
        .order_by(GeoScore.client_id, desc(GeoScore.computed_at))
        .all()
    )
    latest: dict[uuid.UUID, float] = {}
    baseline: dict[uuid.UUID, float] = {}
    for s in scores:
        if s.client_id not in latest:
            latest[s.client_id] = s.overall_score
        if s.client_id not in baseline and s.computed_at < period.start:
            baseline[s.client_id] = s.overall_score

    if not latest:
        return PortfolioHealth(
            average_score=None, average_delta=None, clients_scored=0,
            biggest_gainer=None, biggest_decliner=None,
        )

    deltas = {
        cid: latest[cid] - baseline[cid] for cid in latest if cid in baseline
    }

    def _mover(cid: uuid.UUID) -> DashboardMover:
        return DashboardMover(
            client_id=cid, client_name=name_by_id[cid],
            delta=round(deltas[cid], 1), latest_score=latest[cid],
        )

    gainer_id = max(deltas, key=deltas.__getitem__, default=None)
    decliner_id = min(deltas, key=deltas.__getitem__, default=None)
    return PortfolioHealth(
        average_score=round(sum(latest.values()) / len(latest), 1),
        average_delta=(
            round(sum(deltas.values()) / len(deltas), 1) if deltas else None
        ),
        clients_scored=len(latest),
        biggest_gainer=(
            _mover(gainer_id) if gainer_id is not None and deltas[gainer_id] > 0 else None
        ),
        biggest_decliner=(
            _mover(decliner_id) if decliner_id is not None and deltas[decliner_id] < 0 else None
        ),
    )


def _cost_summary(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> CostSummary:
    # llm_call_logs.called_at is the one AWARE column — aware bounds only here.
    in_period = [
        LlmCallLog.called_at >= period.start_aware,
        LlmCallLog.called_at < period.end_aware,
    ]
    total = (
        db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
        .filter(*in_period)
        .scalar()
    )
    unattributed = (
        db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
        .filter(*in_period, LlmCallLog.client_id.is_(None))
        .scalar()
    )
    top = (
        db.query(
            LlmCallLog.service,
            func.sum(LlmCallLog.cost_usd).label("cost"),
        )
        .filter(*in_period)
        .group_by(LlmCallLog.service)
        .order_by(func.sum(LlmCallLog.cost_usd).desc())
        .first()
    )
    selected = None
    if client_id is not None:
        selected = float(
            db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
            .filter(*in_period, LlmCallLog.client_id == client_id)
            .scalar()
        )
    return CostSummary(
        total_cost_usd=float(total),
        top_service=(
            ServiceCost(service=top.service, cost_usd=float(top.cost))
            if top is not None
            else None
        ),
        unattributed_cost_usd=float(unattributed),
        selected_client_cost_usd=selected,
    )
