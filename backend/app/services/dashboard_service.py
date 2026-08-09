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

from sqlalchemy import desc
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
from app.schemas.dashboard import (
    DashboardFeedItem,
    DashboardFeedResponse,
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
