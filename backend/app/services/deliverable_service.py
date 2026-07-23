# backend/app/services/deliverable_service.py
"""Content deliverable generators — FAQ pack, comparison page, glossary.

Claude writes; the admin gates. Drafts persist immediately; only an explicit
PATCH marks a row reviewed, and regeneration always creates a NEW draft
(reviewed rows are retainer deliverables — never overwritten). Claude
failure → None, nothing persisted (same retryable contract as
content_brief_service).
"""
import json
import uuid

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_deliverable import ContentDeliverable
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.prompts.deliverables import build_comparison_page, build_faq_pack, build_glossary
from app.services.brand_detection import detect_brand_mention
from app.services.claude_client import MODEL_NARRATIVE, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_text

logger = structlog.get_logger()

DELIVERABLE_TYPES = ("faq_pack", "comparison_page", "glossary")
_MAX_TOKENS = 4096
_MAX_LOST_QUERIES = 10

_TYPE_LABELS = {
    "faq_pack": "FAQ pack",
    "comparison_page": "comparison page",
    "glossary": "industry glossary",
}


def _latest_completed_scan(client_id: uuid.UUID, db: Session) -> Scan | None:
    return (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )


def _client_results(scan: Scan, db: Session) -> list[ScanQueryResult]:
    return (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.hallucination_flagged.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .all()
    )


def _build_evidence(
    client: Client, dtype: str, db: Session, competitor: Competitor | None
) -> tuple[str, dict]:
    """(prompt, source_context). source_context is admin-only provenance."""
    scan = _latest_completed_scan(client.id, db)
    results = _client_results(scan, db) if scan else []

    if dtype == "faq_pack":
        lost = [r for r in results if not r.brand_detected][:_MAX_LOST_QUERIES]
        return build_faq_pack(client, [r.query_text for r in lost]), {
            "scan_id": str(scan.id) if scan else None,
            "result_ids": [str(r.id) for r in lost],
        }

    if dtype == "comparison_page":
        evidence_lines: list[str] = []
        used_ids: list[str] = []
        for r in results:
            if r.response_text and detect_brand_mention(r.response_text, competitor.name):
                outcome = "also seen by AI" if r.brand_detected else "seen by AI while the client was not"
                evidence_lines.append(f'Asked "{r.query_text}": {competitor.name} was {outcome}.')
                used_ids.append(str(r.id))
        return build_comparison_page(client, competitor, evidence_lines), {
            "scan_id": str(scan.id) if scan else None,
            "competitor_id": str(competitor.id),
            "result_ids": used_ids,
        }

    # glossary
    query_texts = sorted({r.query_text for r in results})
    return build_glossary(client, query_texts), {
        "scan_id": str(scan.id) if scan else None,
        "query_count": len(query_texts),
    }


def generate_deliverable(
    client: Client, dtype: str, db: Session, competitor: Competitor | None = None
) -> ContentDeliverable | None:
    """Generate + persist one draft deliverable. None = Claude failure
    (nothing persisted, caller surfaces a retryable error)."""
    if dtype not in DELIVERABLE_TYPES:
        raise ValueError(f"unknown deliverable type: {dtype}")
    if dtype == "comparison_page" and competitor is None:
        raise ValueError("comparison_page requires a competitor")

    prompt, source_context = _build_evidence(client, dtype, db, competitor)

    try:
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        record_llm_call(
            service=f"deliverable_{dtype}", model=MODEL_NARRATIVE, response=response,
            client_id=client.id, db=db,
        )
        payload = json.loads(strip_code_fences(response.content[0].text))
        title = sanitize_text(str(payload["title"]).strip())
        body_md = sanitize_text(str(payload["body_md"]).strip())
        if not title or not body_md:
            raise ValueError("deliverable missing title or body")
    except Exception as exc:
        logger.warning(
            "deliverable_generation_failed",
            client_id=str(client.id), type=dtype, error=str(exc),
        )
        return None

    deliverable = ContentDeliverable(
        client_id=client.id,
        type=dtype,
        competitor_id=competitor.id if competitor else None,
        title=title[:512],
        body_md=body_md,
        source_context=source_context,
    )
    db.add(deliverable)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="deliverable_generated",
        note=f"Content deliverable generated: {_TYPE_LABELS[dtype]} — {title[:80]}",
    ))
    db.commit()
    db.refresh(deliverable)
    return deliverable
