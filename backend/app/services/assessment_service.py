from app.core.time import utcnow
# backend/app/services/assessment_service.py
"""Claude-assisted, admin-reviewed scoring for the manual GEO dimensions."""
import json

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.content_analysis import ContentAnalysis
from app.models.dimension_assessment import DimensionAssessment
from app.prompts.assessment import build_assessment_prompt
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL_NARRATIVE
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_bullets  # noqa: F401 — re-exported

logger = structlog.get_logger()

# Headroom for web-search turns, which interleave commentary between searches
# before the final JSON; truncation is caught by the stop_reason guard below.
_MAX_TOKENS = 1500

# Server-side web search so evidence bullets cite real findings instead of
# fabricated review counts (prompt-audit C1). Low volume — assessments run
# on demand only — so the per-search cost is negligible.
_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

_SERVICE_BY_DIMENSION = {
    "brand_authority": "assessment_brand_authority",
    "content_quality": "assessment_content_quality",
}


def _final_text(response) -> str:
    """Last text block of a Claude response.

    Web-search turns return server_tool_use / web_search_tool_result blocks and
    possibly interim text before the final answer — content[0].text is no
    longer the JSON payload.
    """
    texts = [b.text for b in response.content if isinstance(getattr(b, "text", None), str)]
    if not texts:
        raise ValueError("no text block in Claude response")
    return texts[-1]


def _latest_crawl(client_id, db: Session) -> dict | None:
    """Most recent completed crawl, shaped for the content-quality prompt
    (prompt-audit C2: assess the site we actually crawled, not a guess)."""
    row = (
        db.query(ContentAnalysis)
        .filter(ContentAnalysis.client_id == client_id, ContentAnalysis.status == "completed")
        .order_by(desc(ContentAnalysis.analyzed_at))
        .first()
    )
    if row is None:
        return None
    return {
        "pages_crawled": row.pages_crawled,
        "metrics": row.content_metrics_json or {},
        "entity_coverage_score": row.entity_coverage_score,
        "analyzed_at": row.analyzed_at.isoformat() if row.analyzed_at else None,
    }


def generate_assessment(client: Client, dimension: str, db: Session) -> DimensionAssessment | None:
    """Run the Claude assessment for one dimension and persist a `suggested` row.

    Returns None when Claude fails or returns unparseable output — caller
    surfaces a retryable error; nothing is persisted in that case.
    """
    try:
        service = _SERVICE_BY_DIMENSION[dimension]
        crawl = _latest_crawl(client.id, db) if dimension == "content_quality" else None
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=_MAX_TOKENS,
            temperature=0,
            tools=[_WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": build_assessment_prompt(client, dimension, crawl=crawl)}],
        )
        record_llm_call(service=service, model=MODEL_NARRATIVE, response=response, client_id=client.id, db=db)
        if response.stop_reason == "max_tokens":
            # Truncated, not malformed — parsing a partial payload would persist garbage.
            raise ValueError("assessment truncated: stop_reason=max_tokens")
        payload = json.loads(strip_code_fences(_final_text(response)))
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
        generated_at=utcnow(),
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
    row.reviewed_at = utcnow()

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
