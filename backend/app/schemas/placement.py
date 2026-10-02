"""Admin-only placement engine schemas. Never used on the client view: they
carry outreach contacts, competitor positions and in-flight work."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class PlacementTargetOut(BaseModel):
    id: uuid.UUID
    url: str
    domain: str
    title: str | None
    category: str
    status: str
    answers_count: int
    platforms: list[str]
    query_categories: list[str]
    competitors: list[str]  # names, resolved from competitors_present
    other_businesses_listed: int | None
    client_present: bool
    priority_score: int
    priority_reasons: list[str]
    authority_asset_id: uuid.UUID | None
    outcome_action_id: uuid.UUID | None
    last_seen_at: datetime | None
    analyzed_at: datetime | None


class ProofQuestion(BaseModel):
    query_text: str
    platform: str


class PlacementTargetDetail(PlacementTargetOut):
    page_analysis: dict | None
    outreach_drafts: list[dict]
    proof_question: ProofQuestion | None


class PatchPlacementRequest(BaseModel):
    # Pursuing/placed/verified are reached through delivery and proof, never
    # set by hand.
    status: Literal["open", "dismissed"]


class PatchDraftRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


class PursuePlacementRequest(BaseModel):
    due_date: date | None = None
