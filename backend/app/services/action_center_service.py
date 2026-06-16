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
    SCORE_WEIGHTS,
)
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_analysis import ContentAnalysis
from app.models.geo_score import GeoScore
from app.models.scan import Scan
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
    for priority, (lo, hi) in ACTION_PRIORITY_BANDS.items():
        if lo <= impact <= hi:
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

    actions = []
    for item in raw_actions:
        dimension = item.get("dimension")
        action_text = item.get("action_text")
        if dimension not in DIMENSIONS or not action_text:
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
