"""Schemas for the read-only client view (/api/v1/view/{token}).

Every model here is a strict whitelist — never reuse admin schemas. Wire
field names carry the client-facing vocabulary (seen_by_ai, ai_search_ranking,
visibility_frequency) so forbidden terms can't leak into the client UI.
Structurally excluded: response_text, hallucination_flagged, contact_email,
evidence text, score_drop_threshold, estimated_impact, internal ids.
"""
import uuid
from datetime import date, datetime
from pydantic import BaseModel


class ClientViewProfile(BaseModel):
    name: str
    website: str
    industry: str


class ClientViewScore(BaseModel):
    overall_score: float
    ai_visibility: float  # ai_citability on the wire as client-safe name
    brand_authority: float
    content_quality: float
    technical_foundations: float
    structured_data: float
    computed_at: datetime


class ClientViewScorePoint(BaseModel):
    overall_score: float
    computed_at: datetime


class ClientViewTrafficPoint(BaseModel):
    period: date
    ai_visitors: int


class ClientViewPlatform(BaseModel):
    """One AI platform's visibility status. visibility_frequency is None when
    the platform was unavailable during the latest scan."""
    platform_label: str
    seen_by_ai: bool
    visibility_frequency: float | None


class ClientViewBenchmark(BaseModel):
    """Anonymous industry standing — never includes rank or peer identities."""
    industry: str
    peer_count: int
    industry_average: float
    top_percent: int


class ClientViewOverview(BaseModel):
    profile: ClientViewProfile
    latest_score: ClientViewScore | None
    platforms: list[ClientViewPlatform] = []
    benchmark: ClientViewBenchmark | None = None
    score_history: list[ClientViewScorePoint]
    traffic: list[ClientViewTrafficPoint]
    # "What changed this month" narrative from the latest delivered report
    change_narrative: str | None = None
    change_narrative_period: str | None = None


class ClientViewScanResult(BaseModel):
    platform_label: str = "Gemini"
    category: str
    query_text: str
    seen_by_ai: bool
    ai_search_ranking: int | None


class ClientViewScan(BaseModel):
    completed_at: datetime | None
    results: list[ClientViewScanResult]


class ClientViewCompetitorQuery(BaseModel):
    platform_label: str = "Gemini"
    category: str
    query_text: str
    seen_by_ai: bool


class ClientViewCompetitor(BaseModel):
    name: str
    website: str | None
    visibility_frequency: float
    is_winning: bool
    # Keyed by platform label; winning_platform_labels = where this competitor beats the client
    platform_visibility: dict[str, float] = {}
    winning_platform_labels: list[str] = []
    queries: list[ClientViewCompetitorQuery]


class ClientViewCompetitors(BaseModel):
    your_visibility_frequency: float | None
    your_platform_visibility: dict[str, float] = {}
    competitors: list[ClientViewCompetitor]
    last_scan_at: str | None


class ClientViewReport(BaseModel):
    id: uuid.UUID
    period_start: datetime
    period_end: datetime
    overall_score: float
    generated_at: datetime
    download_url: str


class ClientViewAction(BaseModel):
    action_text: str
    dimension: str
    priority: str
    generated_at: datetime


class ClientViewIssueGroup(BaseModel):
    dimension: str
    dimension_label: str
    issues: list[str]


class ClientViewTrendSeries(BaseModel):
    name: str
    is_you: bool
    points: list[float | None]  # visibility frequency per checked date


class ClientViewCompetitorTrends(BaseModel):
    """Dates only — scan ids and internal ids never reach this surface."""
    checked_at: list[datetime]  # oldest → newest
    series: list[ClientViewTrendSeries]
