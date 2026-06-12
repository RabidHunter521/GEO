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


class ClientViewOverview(BaseModel):
    profile: ClientViewProfile
    latest_score: ClientViewScore | None
    score_history: list[ClientViewScorePoint]
    traffic: list[ClientViewTrafficPoint]


class ClientViewScanResult(BaseModel):
    category: str
    query_text: str
    seen_by_ai: bool
    ai_search_ranking: int | None


class ClientViewScan(BaseModel):
    completed_at: datetime | None
    results: list[ClientViewScanResult]


class ClientViewCompetitorQuery(BaseModel):
    category: str
    query_text: str
    seen_by_ai: bool


class ClientViewCompetitor(BaseModel):
    name: str
    website: str | None
    visibility_frequency: float
    is_winning: bool
    queries: list[ClientViewCompetitorQuery]


class ClientViewCompetitors(BaseModel):
    your_visibility_frequency: float | None
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
