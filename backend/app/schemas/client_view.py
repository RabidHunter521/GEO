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
    logo_url: str | None = None
    # Prospects get a deliberately simplified view (overview + scan only).
    is_prospect: bool = False


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
    # Whether deliverable tabs have any content yet — drives tab visibility.
    has_our_work: bool = False
    has_content_plan: bool = False


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


# --- Deliverables surfaced read-only on the client view ----------------------
# Each is a strict whitelist of an admin-side artifact. Internal fields
# (entity_coverage_score, content_metrics, raw verification timing details,
# non-whitelisted activity events) are structurally excluded.


class ClientViewToolkit(BaseModel):
    """AI Readiness files prepared for the client, with live-verification status.
    The file bodies are publishable assets — safe to show with copy/download."""
    llms_txt: str
    schema_json: str
    robots_txt: str
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    verified_at: datetime | None = None
    generated_at: datetime


class ClientViewRoadmapItem(BaseModel):
    week: int
    theme: str
    priority: str
    content_type: str
    suggested_title: str
    rationale: str
    target_queries: list[str] = []
    competitors_winning: list[str] = []
    # Full article draft, shown read-only when the SeenBy team has generated it.
    article_content: str | None = None


class ClientViewRoadmap(BaseModel):
    items: list[ClientViewRoadmapItem]
    source_query_count: int
    generated_at: datetime


class ClientViewTopic(BaseModel):
    topic: str
    status: str  # strong | weak | missing


class ClientViewEntity(BaseModel):
    entity: str
    covered: bool


class ClientViewSuggestedContent(BaseModel):
    topic: str
    title: str
    rationale: str


class ClientViewContentGaps(BaseModel):
    topics: list[ClientViewTopic]
    entities: list[ClientViewEntity]
    suggested_content: list[ClientViewSuggestedContent]
    quality_recommendation: str | None = None
    analyzed_at: datetime


class ClientViewActivity(BaseModel):
    """One client-meaningful activity event. `kind` is a stable key for the UI
    icon; `label` is the friendly headline; `note` is the persisted detail."""
    kind: str
    label: str
    note: str
    created_at: datetime
