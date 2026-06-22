# backend/app/services/assessment_service.py
"""Claude-assisted, admin-reviewed scoring for the manual GEO dimensions."""
import json
import re
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.prompts.assessment import build_assessment_prompt
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL
from app.services.cost_tracker import record_llm_call

logger = structlog.get_logger()

_MAX_TOKENS = 800

# CLAUDE.md §2 — case-insensitive replacements applied to client-facing bullets
# as a safety net behind the prompt's own instructions.
_FORBIDDEN: list[tuple[str, str]] = [
    (r"\bnot mentioned\b", "not seen by AI"),
    (r"\buncited\b", "not seen by AI"),
    (r"\bmentioned\b", "seen by AI"),
    (r"\bcited\b", "seen by AI"),
    (r"\bcitation rate\b", "visibility frequency"),
    (r"\branking position\b", "AI Search Ranking"),
    (r"\bvisibility gap\b", "Your competitors are winning here"),
    (r"\bfirst mentioned\b", "first seen by AI"),
]

_SERVICE_BY_DIMENSION = {
    "brand_authority": "assessment_brand_authority",
    "content_quality": "assessment_content_quality",
}


def sanitize_bullets(bullets: list[str]) -> list[str]:
    """Replace forbidden vocabulary; drop empties. Never raises."""
    cleaned: list[str] = []
    for raw in bullets:
        text = str(raw).strip()
        for pattern, repl in _FORBIDDEN:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        if text:
            cleaned.append(text)
    return cleaned


def generate_assessment(client: Client, dimension: str, db: Session) -> DimensionAssessment | None:
    """Run the Claude assessment for one dimension and persist a `suggested` row.

    Returns None when Claude fails or returns unparseable output — caller
    surfaces a retryable error; nothing is persisted in that case.
    """
    service = _SERVICE_BY_DIMENSION[dimension]
    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": build_assessment_prompt(client, dimension)}],
        )
        record_llm_call(service=service, model=MODEL, response=response, client_id=client.id, db=db)
        payload = json.loads(strip_code_fences(response.content[0].text))
        score = int(payload["score"])
        score = max(0, min(100, score))
        bullets = sanitize_bullets(payload["bullets"])
        narrative = str(payload.get("narrative", "")).strip() or None
        if not bullets:
            raise ValueError("assessment produced no usable evidence bullets")
    except Exception as exc:
        logger.warning(
            "assessment_generation_failed",
            client_id=str(client.id), dimension=dimension, error=str(exc),
        )
        return None

    row = DimensionAssessment(
        client_id=client.id,
        dimension=dimension,
        suggested_score=score,
        evidence_bullets=bullets,
        raw_narrative=narrative,
        status="suggested",
        generated_at=datetime.utcnow(),
    )
    db.add(row)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="assessment_generated",
        note=f"{dimension} assessment generated (suggested {score})",
    ))
    db.commit()
    db.refresh(row)
    return row
