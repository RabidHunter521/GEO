# backend/app/services/assessment_service.py
"""Claude-assisted, admin-reviewed scoring for the manual GEO dimensions."""
import json
from datetime import datetime

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.prompts.assessment import build_assessment_prompt
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_bullets  # noqa: F401 — re-exported

logger = structlog.get_logger()

_MAX_TOKENS = 800

_SERVICE_BY_DIMENSION = {
    "brand_authority": "assessment_brand_authority",
    "content_quality": "assessment_content_quality",
}


def generate_assessment(client: Client, dimension: str, db: Session) -> DimensionAssessment | None:
    """Run the Claude assessment for one dimension and persist a `suggested` row.

    Returns None when Claude fails or returns unparseable output — caller
    surfaces a retryable error; nothing is persisted in that case.
    """
    try:
        service = _SERVICE_BY_DIMENSION[dimension]
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


_SCORE_FIELD = {
    "brand_authority": "brand_authority_score",
    "content_quality": "content_quality_score",
}
_EVIDENCE_FIELD = {
    "brand_authority": "brand_authority_evidence",
    "content_quality": "content_quality_evidence",
}


def latest_assessment(client_id, dimension: str, db: Session) -> DimensionAssessment | None:
    return (
        db.query(DimensionAssessment)
        .filter(DimensionAssessment.client_id == client_id,
                DimensionAssessment.dimension == dimension)
        .order_by(desc(DimensionAssessment.generated_at))
        .first()
    )


def accept_assessment(
    client: Client, dimension: str, final_score: int | None, db: Session
) -> DimensionAssessment | None:
    """Accept (or adjust) the latest suggestion for a dimension.

    Writes the accepted score + denormalized evidence text to the Client row so
    the existing evidence-required invariant and the PDF report keep working.
    Does NOT create a GeoScore row — the value flows into the overall score at
    the next scan, identical to a manual dimension edit today. Returns None when
    there is no suggestion to accept.
    """
    row = latest_assessment(client.id, dimension, db)
    if row is None:
        return None

    accepted = row.suggested_score if final_score is None else max(0, min(100, int(final_score)))
    row.final_score = accepted
    row.status = "accepted" if accepted == row.suggested_score else "adjusted"
    row.reviewed_at = datetime.utcnow()

    setattr(client, _SCORE_FIELD[dimension], accepted)
    setattr(client, _EVIDENCE_FIELD[dimension], "\n".join(row.evidence_bullets))

    db.add(ActivityLog(
        client_id=client.id,
        event_type="assessment_accepted",
        note=f"{dimension} score set to {accepted} ({row.status})",
    ))
    db.commit()
    db.refresh(row)
    return row
