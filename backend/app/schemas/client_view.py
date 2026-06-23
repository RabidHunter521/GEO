"""Schemas for the read-only client view (/api/v1/view/{token}).

Every model here is a strict whitelist — never reuse admin schemas. Wire
field names carry the client-facing vocabulary (seen_by_ai, ai_search_ranking,
visibility_frequency) so forbidden terms can't leak into the client UI.
Structurally excluded: response_text, hallucination_flagged, contact_email,
raw_narrative and admin free-text, score_drop_threshold, estimated_impact,
internal ids. Sanitized, accepted evidence bullets are deliberately surfaced
via brand_authority_evidence and content_quality_evidence on ClientViewScore.
"""
# response_text and raw_narrative are structurally excluded from all schemas in this module.
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
    # Sanitized evidence bullets from accepted/adjusted DimensionAssessment rows.
    # raw_narrative is NEVER included — these are the admin-reviewed bullet points only.
    brand_authority_evidence: list[str] = []
    content_quality_evidence: list[str] = []


class ClientViewProofCard(BaseModel):
    """One verbatim AI answer reduced to a single client-safe sentence. The
    excerpt is competitor-redacted and never contains raw response_text."""
    kind: str            # "win" | "loss"
    platform_label: str
    category: str
    excerpt: str


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


class ClientViewTrafficValue(BaseModel):
    """The single revenue number for the CEO, from the latest month's AI-referral
    visitors. RM fields are None unless the admin has set a deal value."""
    period: date
    ai_visitors: int
    est_leads: int | None = None
    est_pipeline_rm: int | None = None
    est_won_rm: int | None = None


class ClientViewProgressItem(BaseModel):
    """One tracked remediation item, client-safe: the question, the platform, the
    competitors winning it, and where it is in the Flagged -> In progress ->
    Corrected loop. Raw AI responses are never included."""
    item_type: str          # hallucination | content_gap
    type_label: str         # friendly: "Inaccurate AI answer" | "Competitor winning"
    platform_label: str | None = None
    label: str              # the question asked
    detail: str | None = None  # competitors seen, for content gaps
    status: str             # flagged | in_progress | corrected
    status_label: str       # "Flagged" | "In progress" | "Corrected"


class ClientViewOverview(BaseModel):
    profile: ClientViewProfile
    latest_score: ClientViewScore | None
    platforms: list[ClientViewPlatform] = []
    benchmark: ClientViewBenchmark | None = None
    score_history: list[ClientViewScorePoint]
    traffic: list[ClientViewTrafficPoint]
    # Latest-month AI-referral pipeline value (the one money number).
    traffic_value: ClientViewTrafficValue | None = None
    # "What changed this month" narrative from the latest delivered report
    change_narrative: str | None = None
    change_narrative_period: str | None = None
    # Whether deliverable tabs have any content yet — drives tab visibility.
    has_our_work: bool = False
    has_content_plan: bool = False
    # Whether the remediation loop has any tracked items (drives the progress card).
    has_progress: bool = False
    # Count of remediation items corrected within the current calendar month —
    # the "items we fixed this month" proof-of-work stat on the overview hero.
    fixed_this_month: int = 0
    # Verbatim AI-answer proof cards — best wins + best loss from the latest
    # completed scan. Populated for non-prospects only; always [] for prospects.
    # response_text is structurally excluded: only the finished excerpt travels.
    proof_cards: list[ClientViewProofCard] = []
    # Freshness: when the score was last computed, and the next check-in date
    # derived from the client's review cadence. is_stale flags an aged score so
    # the UI shows "next check due ~<date>" instead of a bare old date.
    last_checked_at: datetime | None = None
    next_check_due: date | None = None
    is_stale: bool = False


class ClientViewScanResult(BaseModel):
    platform_label: str = "Gemini"
    category: str
    query_text: str
    seen_by_ai: bool
    ai_search_ranking: int | None
    excerpt: str | None = None
    excerpt_kind: str | None = None  # "win" | "loss" | None


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
    # One-line "so what" — where this competitor is seen by AI relative to you.
    # Derived deterministically from the scan breakdown (no raw AI responses).
    takeaway: str | None = None
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
