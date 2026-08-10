"""Global dashboard response shapes. ADMIN-ONLY — never import from
client_view code paths: CostSummary must not be reachable from any
share-token surface."""
import uuid
from datetime import datetime
from pydantic import BaseModel


class DashboardFeedItem(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    event_type: str
    note: str
    created_at: datetime
    tier: str            # attention | notable | routine
    category: str | None  # None for unmapped (future) event types
    link_path: str       # absolute admin path, e.g. /clients/<id>/scan


class DashboardFeedResponse(BaseModel):
    items: list[DashboardFeedItem]
    total: int
    has_more: bool


class AttentionCounts(BaseModel):
    scans_failed: int
    platforms_unavailable: int
    scans_blocked_budget: int
    hallucinations_flagged: int
    alerts_sent: int
    share_of_source_changes: int


class DashboardMover(BaseModel):
    client_id: uuid.UUID
    client_name: str
    delta: float
    latest_score: float


class PortfolioHealth(BaseModel):
    average_score: float | None   # None when no active client has a score
    average_delta: float | None   # None when no client has a pre-period baseline
    clients_scored: int
    biggest_gainer: DashboardMover | None   # only when its delta > 0
    biggest_decliner: DashboardMover | None  # only when its delta < 0


class ServiceCost(BaseModel):
    service: str
    cost_usd: float


class CostSummary(BaseModel):
    total_cost_usd: float
    top_service: ServiceCost | None
    unattributed_cost_usd: float          # rows whose client was deleted (SET NULL)
    selected_client_cost_usd: float | None  # only when a client filter is active


class DashboardSummaryResponse(BaseModel):
    attention: AttentionCounts
    portfolio: PortfolioHealth
    cost: CostSummary
