from app.core.time import utcnow
# backend/app/services/action_center_service.py
"""Claude-powered GEO Action Center: 3-5 prioritized actions with an estimated
score impact, regenerated after every completed scan.

Impact numbers are always computed deterministically server-side — Claude
categorises each action's effort level ("quick-win", "medium-term", "long-term"),
which maps to a canonical gap fraction. That fraction drives estimated_impact so
the numbers stay internally consistent and auditable without requiring Claude to
estimate a precise float.
"""
import json

import structlog
from sqlalchemy.orm import Session

from app.core.constants import (
    ACTION_IMPACT_MAX_PER_ACTION,
    ACTION_PRIORITY_BANDS,
    MAX_OPEN_ACTIONS,
    SCORE_WEIGHTS,
)
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_analysis import ContentAnalysis
from app.models.geo_score import GeoScore
from app.models.scan_query_result import ScanQueryResult
from app.prompts.action_center import DIMENSIONS, build as build_prompt
from app.services.claude_client import MODEL_NARRATIVE, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call

logger = structlog.get_logger()


def _dimension_scores(geo_score: GeoScore) -> dict[str, float]:
    return {dim: float(getattr(geo_score, dim)) for dim in DIMENSIONS}


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


def _priority_for_impact(impact: float) -> str:
    # Bands are ordered high→medium→low; match on the lower bound only so a
    # fractional impact (e.g. 5.5) between two integer bands is never dropped
    # to "low" by an upper-bound miss.
    for priority, (lo, _hi) in ACTION_PRIORITY_BANDS.items():
        if impact >= lo:
            return priority
    return "low"


def generate_actions(client: Client, geo_score: GeoScore, db: Session) -> list[dict]:
    scores = _dimension_scores(geo_score)
    missing_topics = _missing_topics(client, db)
    competitor_winning = _competitor_winning(client, geo_score, db)

    prompt = build_prompt(client, scores, missing_topics, competitor_winning)

    try:
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        record_llm_call(
            service="action_center",
            model=MODEL_NARRATIVE,
            response=response,
            client_id=client.id,
            db=db,
        )
        raw = strip_code_fences(response.content[0].text)
        data = json.loads(raw)
        raw_actions = data.get("actions", []) if isinstance(data, dict) else []
    except Exception:
        logger.warning("action_center_generation_failed", client_id=str(client.id))
        return []

    # Canonical fractions per effort band — Claude judges the category,
    # the server owns the number. quick-win closes more of the gap sooner.
    _effort_fractions = {"quick-win": 0.40, "medium-term": 0.20, "long-term": 0.08}

    actions = []
    for item in raw_actions:
        dimension = item.get("dimension")
        action_text = item.get("action_text")
        if dimension not in DIMENSIONS or not action_text:
            continue

        effort = str(item.get("effort", "medium-term")).strip().lower()
        fraction = _effort_fractions.get(effort, 0.20)
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
        action.resolved_at = utcnow()

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
            generated_at=utcnow(),
        ))

    db.commit()
    logger.info("action_center_refreshed", client_id=str(client.id), action_count=len(new_actions))
