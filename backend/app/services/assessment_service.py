from app.core.time import utcnow
# backend/app/services/assessment_service.py
"""Claude-assisted, admin-reviewed scoring for the manual GEO dimensions."""
import json

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core import request_identity
from app.core.constants import (
    ASSESSMENT_MAX_BULLETS,
    ASSESSMENT_MIN_REASON_CHARS,
    ASSESSMENT_REVIEW_DAYS,
)
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.content_analysis import ContentAnalysis
from app.models.dimension_assessment import DimensionAssessment
from app.prompts.assessment import build_assessment_prompt
from app.services import assessment_rubric, authority_service
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL_NARRATIVE
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_bullets, sanitize_text

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
        authority = (
            authority_service.summarize_for_assessment(client.id, db)
            if dimension == "brand_authority" else None
        )
        measured = assessment_rubric.measure(client, dimension, db)
        judged_def = assessment_rubric.judged_criterion(dimension)
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=_MAX_TOKENS,
            temperature=0,
            tools=[_WEB_SEARCH_TOOL],
            messages=[{"role": "user",
                       "content": build_assessment_prompt(client, dimension, crawl=crawl, authority=authority)}],
        )
        record_llm_call(service=service, model=MODEL_NARRATIVE, response=response, client_id=client.id, db=db)
        if response.stop_reason == "max_tokens":
            # Truncated, not malformed — parsing a partial payload would persist garbage.
            raise ValueError("assessment truncated: stop_reason=max_tokens")
        payload = json.loads(strip_code_fences(_final_text(response)))
        judged_points = max(0, min(judged_def["max"], int(payload["points"])))
        judged_bullets = sanitize_bullets(payload["bullets"])
        narrative = str(payload.get("narrative", "")).strip() or None
        if not judged_bullets:
            raise ValueError("assessment produced no usable evidence bullets")
        criteria = [
            *({**c, "final_points": None} for c in measured),
            {
                "key": judged_def["key"], "label": judged_def["label"],
                "max": judged_def["max"], "basis": "judged", "points": judged_points,
                "evidence": None, "admin_hint": None, "final_points": None,
            },
        ]
        # Rubric order, so the checklist reads the same everywhere.
        order = [c["key"] for c in assessment_rubric.criteria(dimension)]
        criteria.sort(key=lambda c: order.index(c["key"]))
        score = sum(c["points"] for c in criteria)
        # One client-safe line per measured criterion that has something to
        # show, then the reviewed coverage/expertise evidence.
        bullets = [
            sanitize_text(f"{c['label']}: {c['evidence']}")
            for c in criteria if c["evidence"]
        ] + judged_bullets
        bullets = bullets[:ASSESSMENT_MAX_BULLETS]
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
        criteria=criteria,
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


REVIEWED_STATUSES = ("accepted", "adjusted")


def latest_reviewed(client_id, dimension: str, db: Session) -> DimensionAssessment | None:
    """The most recent assessment an admin accepted or adjusted.

    The score on the Client row came from this row, so it is the one whose
    evidence a client may see. A newer suggestion nobody has reviewed yet must
    not hide it (the client view used to read only the latest row, so
    generating a suggestion blanked the reviewed evidence), and a dimension
    with no reviewed row has not been reviewed, whatever its score.
    """
    return (
        db.query(DimensionAssessment)
        .filter(DimensionAssessment.client_id == client_id,
                DimensionAssessment.dimension == dimension,
                DimensionAssessment.status.in_(REVIEWED_STATUSES))
        .order_by(desc(DimensionAssessment.reviewed_at), desc(DimensionAssessment.generated_at))
        .first()
    )


class ReviewError(ValueError):
    """The review cannot be saved as submitted (e.g. a change without a reason)."""


def accept_assessment(
    client: Client,
    dimension: str,
    final_score: int | None,
    db: Session,
    *,
    reason: str | None = None,
    bullets: list[str] | None = None,
    points: dict[str, int] | None = None,
) -> DimensionAssessment | None:
    """Accept, or adjust, the latest suggestion for a dimension.

    Any difference from the suggestion (score or evidence) is an adjustment and
    needs a reason (ReviewError otherwise), so every number a client sees either
    is the suggestion or carries a written why. Records the reviewer, writes the
    score and the evidence that will be shown to the Client row (where scoring
    and the PDF read them). Does NOT create a GeoScore: the value flows into the
    overall score at the next scan. Returns None when there is no suggestion.

    A checklist assessment (v1.6.0+) is adjusted per criterion through
    `points` ({criterion_key: points}); its total is the sum and `final_score`
    is ignored. A pre-checklist row still takes `final_score`.
    """
    row = latest_assessment(client.id, dimension, db)
    if row is None:
        return None

    finals = None
    if row.criteria:
        known = {c["key"] for c in row.criteria}
        unknown = set(points or {}) - known
        if unknown:
            raise ReviewError(f"Unknown checklist item(s): {', '.join(sorted(unknown))}.")
        finals = []
        for c in row.criteria:
            p = c["points"]
            if points and c["key"] in points:
                p = max(0, min(int(c["max"]), int(points[c["key"]])))
            finals.append({**c, "final_points": p})
        accepted = sum(c["final_points"] for c in finals)
    else:
        accepted = row.suggested_score if final_score is None else max(0, min(100, int(final_score)))
    edited = None
    if bullets is not None:
        edited = sanitize_bullets(bullets)[:ASSESSMENT_MAX_BULLETS]
        if not edited:
            raise ReviewError("Keep at least one evidence point.")
        if edited == list(row.evidence_bullets):
            edited = None
    overridden = bool(finals) and any(c["final_points"] != c["points"] for c in finals)
    changed = accepted != row.suggested_score or edited is not None or overridden
    reason = " ".join((reason or "").split()) or None
    if changed and (reason is None or len(reason) < ASSESSMENT_MIN_REASON_CHARS):
        raise ReviewError(
            "Say why you changed the suggestion "
            f"(at least {ASSESSMENT_MIN_REASON_CHARS} characters)."
        )

    row.final_score = accepted
    if finals is not None:
        row.criteria = finals  # reassigned so the JSON change is persisted
    row.final_bullets = edited
    row.status = "adjusted" if changed else "accepted"
    row.adjustment_reason = reason if changed else None
    row.reviewed_by = request_identity.current_name() or "SeenBy admin"
    row.reviewed_at = utcnow()

    setattr(client, _SCORE_FIELD[dimension], accepted)
    setattr(client, _EVIDENCE_FIELD[dimension], "\n".join(row.shown_bullets))

    note = f"{dimension} score set to {accepted} ({row.status})"
    if changed:
        note += f": {reason}"
    db.add(ActivityLog(client_id=client.id, event_type="assessment_accepted", note=note))
    db.commit()
    db.refresh(row)
    return row


def review_due(client: Client, db: Session, now=None) -> list[dict]:
    """Dimensions of `client` whose reviewed score is missing or out of date."""
    now = now or utcnow()
    due = []
    for dimension in _SCORE_FIELD:
        row = latest_reviewed(client.id, dimension, db)
        if row is None:
            due.append({"dimension": dimension, "last_reviewed_at": None, "reason": "never_reviewed"})
        elif not row.criteria:
            # Reviewed before the points checklist (SCORE_VERSION v1.6.0).
            due.append({"dimension": dimension, "last_reviewed_at": row.reviewed_at, "reason": "method_changed"})
        elif row.reviewed_at is None or (now - row.reviewed_at).days >= ASSESSMENT_REVIEW_DAYS:
            due.append({"dimension": dimension, "last_reviewed_at": row.reviewed_at, "reason": "stale"})
    return due
