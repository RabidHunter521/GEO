# backend/app/services/client_period_summary_service.py
"""Deterministic client-facing period summary (Phase 1, Task 4).

A read-only projection over rows other services already produce: GeoScore,
RemediationItem, ActionRecommendation, WorkLogEntry, and scan proof-card
excerpts. It adds no tables and generates nothing.

This feeds the PUBLIC client view (/view/{token}), which is stricter than the
admin Command Center (app/services/command_center_service.py, whose pattern
this mirrors):

  - Deterministic templates only. Every sentence is assembled from a stored
    value — no LLM call, ever.
  - Only WorkLogEntry.status == "published" rows are ever read
    (work_log_service.published_entries filters status at the query, not
    merely by omitting a field from a schema — a `suggested` row can never
    leak here even if this file's logic has a bug elsewhere).
  - Only RemediationItem.item_type in ("hallucination", "content_gap") is
    ever read. "misinformation" items are compliance-workflow-only and stay
    off every client surface until Premium gating exists (CLAUDE.md, spec 8
    §4) — this allowlist mirrors app.api.v1.client_view._REMEDIATION_TYPE_LABELS
    and must be kept in sync with it.
  - Proof-card excerpts are the already-redacted, client-safe strings
    proof_card_service produces; raw response_text never appears here.
  - Each returned list is capped at 3 items.
"""
from datetime import timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS, SCORE_DISPLAY_LABEL, WORK_LOG_CATEGORY_LABELS
from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.client_view import ClientViewPeriodSummary
from app.services import work_log_service
from app.services.proof_card_service import select_proof_cards
from app.services.remediation_service import get_remediation_items

# Client-safe dimension names for next_actions. Deliberately NOT
# app.prompts.action_center.DIMENSION_LABELS, which is written for an
# admin-only surface and uses "AI Citability" — the public client view
# renames this dimension "AI Presence" everywhere else (client_view.py's
# ai_visibility wire field, frontend product-language.ts), and
# command_center_service.py already sets the precedent of a literal
# client-facing label rather than reusing the admin prompt vocabulary.
_DIMENSION_LABELS: dict[str, str] = {
    "ai_citability": "AI Presence",
    "brand_authority": "Brand Authority",
    "content_quality": "Content Quality",
    "technical_foundations": "Technical Foundations",
    "structured_data": "Structured Data",
}

# Remediation item types that are ever client-visible. Mirrors
# app.api.v1.client_view._REMEDIATION_TYPE_LABELS — "misinformation" is
# deliberately excluded (compliance-workflow-only, spec 8 §4).
_REMEDIATION_TYPE_LABELS: dict[str, str] = {
    "hallucination": "Inaccurate AI answer",
    "content_gap": "Competitor winning",
}

_MAX_ITEMS = 3
_WORK_LOG_WINDOW_DAYS = 30


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.title())


def _latest_scores(client: Client, db: Session) -> tuple[GeoScore | None, GeoScore | None]:
    """The two newest scores, newest first. id breaks computed_at ties."""
    rows = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
        .limit(2)
        .all()
    )
    return (rows[0] if rows else None, rows[1] if len(rows) > 1 else None)


def _headline(latest: GeoScore | None, previous: GeoScore | None) -> str:
    if latest is None:
        return "Your first scan is being prepared."
    if previous is None:
        return f"{SCORE_DISPLAY_LABEL} baseline established at {latest.overall_score:.1f} this period."
    delta = round(latest.overall_score - previous.overall_score, 1)
    if delta > 0:
        return f"{SCORE_DISPLAY_LABEL} rose {delta:.1f} points to {latest.overall_score:.1f} this period."
    if delta < 0:
        return (
            f"{SCORE_DISPLAY_LABEL} fell {abs(delta):.1f} points to "
            f"{latest.overall_score:.1f} this period."
        )
    return f"{SCORE_DISPLAY_LABEL} held steady at {latest.overall_score:.1f} this period."


def _score_win(latest: GeoScore | None, previous: GeoScore | None) -> list[str]:
    if latest is None or previous is None:
        return []
    delta = round(latest.overall_score - previous.overall_score, 1)
    if delta <= 0:
        return []
    return [
        f"{SCORE_DISPLAY_LABEL} improved by {delta:.1f} points, from "
        f"{previous.overall_score:.1f} to {latest.overall_score:.1f}."
    ]


def _score_risk(latest: GeoScore | None, previous: GeoScore | None) -> list[str]:
    if latest is None or previous is None:
        return []
    delta = round(latest.overall_score - previous.overall_score, 1)
    if delta >= 0:
        return []
    return [
        f"{SCORE_DISPLAY_LABEL} fell by {abs(delta):.1f} points, from "
        f"{previous.overall_score:.1f} to {latest.overall_score:.1f}."
    ]


def _proof_card_sentences(client: Client, db: Session) -> tuple[list[str], list[str]]:
    """(win sentences, loss sentences) from the latest completed scan's
    client-owned results — the same source the overview's proof_cards field
    already uses. Excerpts are the redacted, sentence-bounded strings
    proof_card_service builds; response_text itself never leaves this
    function."""
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return [], []
    scan_results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(False),
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )
    competitor_names = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    cards = select_proof_cards(scan_results, client.name, competitor_names)
    wins = [
        f'{_platform_label(c.platform)} named you directly: "{c.excerpt}"'
        for c in cards if c.kind == "win"
    ]
    losses = [
        f'{_platform_label(c.platform)} named a competitor instead of you: "{c.excerpt}"'
        for c in cards if c.kind == "loss"
    ]
    return wins, losses


def _work_log_wins(client: Client, db: Session) -> list[str]:
    """Recently PUBLISHED work only — status is filtered at the query inside
    work_log_service.published_entries, never merely by schema omission."""
    since = (utcnow() - timedelta(days=_WORK_LOG_WINDOW_DAYS)).date()
    entries = work_log_service.published_entries(client.id, db, since=since, limit=_MAX_ITEMS)
    return [
        f"{WORK_LOG_CATEGORY_LABELS.get(e.category, e.category.title())} delivered: {e.description}"
        for e in entries
    ]


def _remediation_sentences(client: Client, db: Session) -> tuple[list[str], list[str]]:
    """(risk sentences from flagged items, work-underway sentences from
    in_progress items). Corrected items are deliberately not repeated here —
    the overview hero already reports fixed_this_month, and the work-log wins
    above already cover delivered corrections."""
    items = [
        i for i in get_remediation_items(client.id, db, include_corrected=False)
        if i.item_type in _REMEDIATION_TYPE_LABELS
    ]
    risks: list[str] = []
    underway: list[str] = []
    for i in items:
        type_label = _REMEDIATION_TYPE_LABELS[i.item_type]
        platform = f" on {_platform_label(i.platform)}" if i.platform else ""
        detail = f" (competitors seen: {i.detail})" if i.detail else ""
        sentence = f'{type_label}{platform}: "{i.label}"{detail}'
        if i.status == "flagged":
            risks.append(sentence)
        elif i.status == "in_progress":
            underway.append(sentence)
    return risks, underway


def _next_actions(client: Client, db: Session) -> list[str]:
    rows = (
        db.query(ActionRecommendation)
        .filter(
            ActionRecommendation.client_id == client.id,
            ActionRecommendation.status == "open",
        )
        .order_by(desc(ActionRecommendation.estimated_impact), desc(ActionRecommendation.generated_at))
        .limit(_MAX_ITEMS)
        .all()
    )
    out = []
    for a in rows:
        label = _DIMENSION_LABELS.get(a.dimension, a.dimension.replace("_", " ").title())
        out.append(f"{label}: {a.action_text}")
    return out


def build_client_period_summary(client: Client, db: Session) -> ClientViewPeriodSummary:
    """Aggregate one client's stored evidence into a deterministic, plain-
    English summary. Read-only; never calls an LLM.

    Prospects get a deliberately limited view (overview + scan only) on
    every other part of this surface — proof cards are always [] for a
    prospect, and /progress, /actions and /work-log 404 outright
    (require_non_prospect_share_client). This mirrors that restriction: a
    prospect gets only the score-derived headline, never the retainer-work
    lists, so this summary can't become the one path that leaks premium
    evidence to a not-yet-paying lead.
    """
    latest, previous = _latest_scores(client, db)
    headline = _headline(latest, previous)

    if client.is_prospect:
        return ClientViewPeriodSummary(headline=headline)

    win_cards, loss_cards = _proof_card_sentences(client, db)
    work_log_wins = _work_log_wins(client, db)
    remediation_risks, work_underway = _remediation_sentences(client, db)

    wins = (_score_win(latest, previous) + work_log_wins + win_cards)[:_MAX_ITEMS]
    risks = (_score_risk(latest, previous) + remediation_risks + loss_cards)[:_MAX_ITEMS]

    return ClientViewPeriodSummary(
        headline=headline,
        wins=wins,
        risks=risks,
        work_underway=work_underway[:_MAX_ITEMS],
        next_actions=_next_actions(client, db),
    )
