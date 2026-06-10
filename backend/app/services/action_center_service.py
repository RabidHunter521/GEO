# backend/app/services/action_center_service.py
"""Claude-powered GEO Action Center: 3-5 prioritized actions with an estimated
score impact, regenerated after every completed scan.

Impact numbers are always computed deterministically server-side from a
Claude-suggested "closable gap fraction" — never trusted directly from Claude —
so the displayed "Estimated Impact" stays internally consistent and auditable.
"""
import json
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from app.core.constants import (
    ACTION_IMPACT_MAX_PER_ACTION,
    ACTION_PRIORITY_BANDS,
    MAX_OPEN_ACTIONS,
    SCORE_BANDS,
    SCORE_WEIGHTS,
)
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_analysis import ContentAnalysis
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences

logger = structlog.get_logger()

_DIMENSIONS = (
    "ai_citability",
    "brand_authority",
    "content_quality",
    "technical_foundations",
    "structured_data",
)

_DIMENSION_LABELS = {
    "ai_citability": "AI Citability",
    "brand_authority": "Brand Authority",
    "content_quality": "Content Quality",
    "technical_foundations": "Technical Foundations",
    "structured_data": "Structured Data",
}


def _dimension_scores(geo_score: GeoScore) -> dict[str, float]:
    return {dim: float(getattr(geo_score, dim)) for dim in _DIMENSIONS}


def _missing_topics(client: Client, db: Session) -> list[str]:
    analysis = (
        db.query(ContentAnalysis)
        .filter(ContentAnalysis.client_id == client.id, ContentAnalysis.status == "completed")
        .order_by(ContentAnalysis.analyzed_at.desc())
        .first()
    )
    if not analysis:
        return []
    return [t["topic"] for t in analysis.topics_json if t.get("status") == "missing"][:5]


def _competitor_winning(client: Client, geo_score: GeoScore, db: Session) -> bool:
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    if not competitors:
        return False

    results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == geo_score.scan_id, ScanQueryResult.competitor_id.isnot(None))
        .all()
    )
    by_competitor: dict = {}
    for r in results:
        by_competitor.setdefault(r.competitor_id, []).append(r.brand_detected)

    for detections in by_competitor.values():
        if not detections:
            continue
        citability = (sum(1 for d in detections if d) / len(detections)) * 100
        if citability > geo_score.ai_citability:
            return True
    return False


def _build_prompt(client: Client, scores: dict[str, float], missing_topics: list[str], competitor_winning: bool) -> str:
    score_lines = []
    for dim in _DIMENSIONS:
        score = scores[dim]
        band = next((name for name, (lo, hi) in SCORE_BANDS.items() if lo <= int(score) <= hi), "low")
        score_lines.append(
            f"- {_DIMENSION_LABELS[dim]} ({dim}): {score:.0f}/100, weight {SCORE_WEIGHTS[dim] * 100:.0f}%, band: {band}"
        )

    context_lines = []
    if missing_topics:
        context_lines.append("Topics not yet covered on the website: " + ", ".join(missing_topics))
    if competitor_winning:
        context_lines.append("At least one competitor currently appears in AI answers more often than this business.")

    context_block = "\n".join(context_lines) if context_lines else "No additional context available."

    return f"""You are a GEO (Generative Engine Optimization) advisor for a {client.industry} business
called {client.name}. Their AI visibility score breaks down into 5 dimensions:

{chr(10).join(score_lines)}

Additional context:
{context_block}

Suggest 3-5 specific, practical actions this business could take to improve their AI visibility
score, prioritizing dimensions that are weakest and have the highest weight. For each action:
- action_text: one specific, plain-English sentence describing the action. Use phrases like
  "Your competitors are winning here" instead of "visibility gap", and never use the words
  "citation", "ranking position", "confidence", or "token".
- dimension: which one of {", ".join(_DIMENSIONS)} this action primarily improves.
- closable_gap_fraction: your estimate (0.0 to 1.0) of how much of that dimension's remaining
  gap to 100 this single action could realistically close.

Output ONLY valid JSON, no code fences, in exactly this shape:
{{"actions": [{{"action_text": "string", "dimension": "string", "closable_gap_fraction": 0.0}}]}}"""


def _priority_for_impact(impact: float) -> str:
    for priority, (lo, hi) in ACTION_PRIORITY_BANDS.items():
        if lo <= impact <= hi:
            return priority
    return "low"


def generate_actions(client: Client, geo_score: GeoScore, db: Session) -> list[dict]:
    scores = _dimension_scores(geo_score)
    missing_topics = _missing_topics(client, db)
    competitor_winning = _competitor_winning(client, geo_score, db)

    prompt = _build_prompt(client, scores, missing_topics, competitor_winning)

    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = strip_code_fences(response.content[0].text)
        data = json.loads(raw)
        raw_actions = data.get("actions", []) if isinstance(data, dict) else []
    except Exception:
        logger.warning("action_center_generation_failed", client_id=str(client.id))
        return []

    actions = []
    for item in raw_actions:
        dimension = item.get("dimension")
        action_text = item.get("action_text")
        if dimension not in _DIMENSIONS or not action_text:
            continue

        fraction = max(0.0, min(1.0, float(item.get("closable_gap_fraction", 0.0))))
        remaining_gap = 100.0 - scores[dimension]
        estimated_impact = round(
            min(fraction * remaining_gap * SCORE_WEIGHTS[dimension], ACTION_IMPACT_MAX_PER_ACTION), 1
        )

        actions.append({
            "action_text": action_text,
            "dimension": dimension,
            "estimated_impact": estimated_impact,
            "priority": _priority_for_impact(estimated_impact),
        })

    actions.sort(key=lambda a: a["estimated_impact"], reverse=True)
    return actions[:MAX_OPEN_ACTIONS]


def refresh_actions_for_client(client: Client, geo_score: GeoScore, db: Session) -> None:
    open_actions = (
        db.query(ActionRecommendation)
        .filter(ActionRecommendation.client_id == client.id, ActionRecommendation.status == "open")
        .all()
    )
    for action in open_actions:
        action.status = "superseded"
        action.resolved_at = datetime.utcnow()

    new_actions = generate_actions(client, geo_score, db)
    for action in new_actions:
        db.add(ActionRecommendation(
            client_id=client.id,
            geo_score_id=geo_score.id,
            action_text=action["action_text"],
            dimension=action["dimension"],
            estimated_impact=action["estimated_impact"],
            priority=action["priority"],
            status="open",
            generated_at=datetime.utcnow(),
        ))

    db.commit()
    logger.info("action_center_refreshed", client_id=str(client.id), action_count=len(new_actions))
