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
  - `history` (GeoScore rows) and `proof_cards` are passed in by the caller
    (client_view.get_overview), which already computed both for its own
    response fields. This function must never re-derive them: doing so let
    the headline quote a different scan or a different score than the
    sections rendered directly beneath it whenever a tie in ordering fell
    differently across the two independent queries (Task 4 review, I4).
    Sharing one query result makes that structurally impossible, and drops
    ~4 redundant queries per page load.
  - Proof-card excerpts are the already-redacted, client-safe strings
    proof_card_service produces; raw response_text never appears here.
  - Each returned list is capped at 3 items.
"""
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS, SCORE_DISPLAY_LABEL, WORK_LOG_CATEGORY_LABELS
from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.schemas.client_view import ClientViewPeriodSummary, ClientViewProofCard
from app.services import work_log_service
from app.services.remediation_service import get_remediation_items
from datetime import timedelta

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

# The client-facing "period" this surface uses everywhere else
# (improvements_last_30d on /overview, the monthly PDF report cadence). Two
# scores within this many days of each other can honestly be described as
# "this period"; further apart than that, the headline must name the actual
# comparison date instead of asserting a window the data doesn't support.
_PERIOD_WINDOW_DAYS = _WORK_LOG_WINDOW_DAYS


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.title())


def _latest_scores(history: list[GeoScore]) -> tuple[GeoScore | None, GeoScore | None]:
    """The two newest scores from the caller-supplied history, newest first."""
    latest = history[0] if history else None
    previous = history[1] if len(history) > 1 else None
    return latest, previous


def _score_comparison_basis(latest: GeoScore, previous: GeoScore) -> str:
    """"this period" is only true when the two scores fall within the same
    30-day window this surface uses everywhere else. When they're further
    apart, name the actual date instead of asserting a period the data
    doesn't support (Task 4 review, I3)."""
    gap_days = (latest.computed_at - previous.computed_at).days
    if gap_days <= _PERIOD_WINDOW_DAYS:
        return "this period"
    return f"since your last check on {previous.computed_at:%B %d, %Y}"


def _headline(latest: GeoScore | None, previous: GeoScore | None) -> str:
    if latest is None:
        return "Your first scan is being prepared."
    if previous is None:
        return f"{SCORE_DISPLAY_LABEL} baseline established at {latest.overall_score:.1f}."
    basis = _score_comparison_basis(latest, previous)
    delta = round(latest.overall_score - previous.overall_score, 1)
    if delta > 0:
        return f"{SCORE_DISPLAY_LABEL} rose {delta:.1f} points to {latest.overall_score:.1f} {basis}."
    if delta < 0:
        return (
            f"{SCORE_DISPLAY_LABEL} fell {abs(delta):.1f} points to "
            f"{latest.overall_score:.1f} {basis}."
        )
    return f"{SCORE_DISPLAY_LABEL} held steady at {latest.overall_score:.1f} {basis}."


def _proof_card_sentences(proof_cards: list[ClientViewProofCard]) -> tuple[list[str], list[str]]:
    """(win sentences, loss sentences) built from the already-computed,
    client-safe proof cards the overview's own proof_cards field uses —
    passed in by the caller, never re-derived (Task 4 review, I4)."""
    wins = [
        f'{pc.platform_label} named you directly: "{pc.excerpt}"'
        for pc in proof_cards if pc.kind == "win"
    ]
    losses = [
        f'{pc.platform_label} named a competitor instead of you: "{pc.excerpt}"'
        for pc in proof_cards if pc.kind == "loss"
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


def build_client_period_summary(
    client: Client,
    db: Session,
    history: list[GeoScore],
    proof_cards: list[ClientViewProofCard],
) -> ClientViewPeriodSummary:
    """Aggregate one client's stored evidence into a deterministic, plain-
    English summary. Read-only; never calls an LLM.

    `history` (newest-first, with a total ordering — ties broken by id) and
    `proof_cards` must be the exact values the caller already built for its
    own response fields; see the module docstring for why this function
    never re-queries them itself.

    Prospects get a deliberately limited view (overview + scan only) on
    every other part of this surface — proof cards are always [] for a
    prospect, and /progress, /actions and /work-log 404 outright
    (require_non_prospect_share_client). This mirrors that restriction: a
    prospect gets only the score-derived headline, never the retainer-work
    lists, so this summary can't become the one path that leaks premium
    evidence to a not-yet-paying lead.
    """
    latest, previous = _latest_scores(history)
    headline = _headline(latest, previous)

    if client.is_prospect:
        return ClientViewPeriodSummary(headline=headline)

    win_cards, loss_cards = _proof_card_sentences(proof_cards)
    work_log_wins = _work_log_wins(client, db)
    remediation_risks, work_underway = _remediation_sentences(client, db)

    # Score movement is already stated in the headline above — repeating it
    # here would consume one of only three list slots without adding new
    # information, pushing actual delivered work or tracked risk detail off
    # the card (Task 4 review, M1).
    wins = (work_log_wins + win_cards)[:_MAX_ITEMS]
    risks = (remediation_risks + loss_cards)[:_MAX_ITEMS]

    return ClientViewPeriodSummary(
        headline=headline,
        wins=wins,
        risks=risks,
        work_underway=work_underway[:_MAX_ITEMS],
        next_actions=_next_actions(client, db),
    )
