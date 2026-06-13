import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: str | None = Field(default=None, max_length=500)


class CompetitorResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    website: str | None = None

    model_config = {"from_attributes": True}


class CompetitorQueryBreakdown(BaseModel):
    platform: str = "gemini"
    category: str
    query_text: str
    brand_detected: bool


class CompetitorScore(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None = None
    ai_citability: float
    queries: list[CompetitorQueryBreakdown]
    is_winning: bool
    # Visibility frequency per platform, and platforms where this competitor beats the client
    platform_visibility: dict[str, float] = {}
    winning_platforms: list[str] = []


class CompetitorIntelligenceResponse(BaseModel):
    client_ai_citability: float | None
    client_platform_visibility: dict[str, float] = {}
    competitors: list[CompetitorScore]
    last_scan_at: str | None


# ── Win/loss analysis (admin only — never reuse on the client view) ──────────

class ContentBriefResponse(BaseModel):
    id: uuid.UUID
    title: str
    angle: str
    outline: list[str]
    competitors_seen: list[str]
    generated_at: datetime

    model_config = {"from_attributes": True}


class WinLossEntry(BaseModel):
    result_id: uuid.UUID
    platform: str
    category: str
    query_text: str
    client_seen: bool
    competitors_seen: list[str]
    outcome: Literal["won", "lost", "shared", "open"]
    brief: ContentBriefResponse | None = None


class WinLossResponse(BaseModel):
    scan_id: uuid.UUID | None
    last_scan_at: str | None
    summary: dict[str, int]
    entries: list[WinLossEntry]


# ── Visibility trends ─────────────────────────────────────────────────────────

class TrendScanPoint(BaseModel):
    scan_id: uuid.UUID
    completed_at: datetime


class TrendSeries(BaseModel):
    competitor_id: uuid.UUID | None  # None = the client
    name: str
    points: list[float | None]  # aligned to scans, oldest → newest


class CompetitorTrendsResponse(BaseModel):
    scans: list[TrendScanPoint]
    client: TrendSeries
    competitors: list[TrendSeries]
