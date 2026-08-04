from app.core.time import utcnow
# backend/app/services/content_brief_service.py
"""On-demand Claude content briefs for queries the client lost to competitors."""
import json

import structlog
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.content_brief import ContentBrief
from app.prompts.content_brief import build_content_brief
from app.models.scan_query_result import ScanQueryResult
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL, was_truncated
from app.services.cost_tracker import record_llm_call
from app.services.pack_query_service import pack_context_for

logger = structlog.get_logger()

_MAX_TOKENS = 1024


def generate_brief_for_result(
    client: Client,
    result: ScanQueryResult,
    competitors_seen: list[str],
    db: Session,
) -> ContentBrief | None:
    """Generate (or regenerate) a brief for one lost/open query result.

    Returns None when Claude fails or returns unparseable output — caller
    surfaces a retryable error; nothing is persisted in that case.
    """
    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": build_content_brief(client, result, competitors_seen, *pack_context_for(client, db))}],
        )
        record_llm_call(
            service="content_brief", model=MODEL, response=response, client_id=client.id, db=db
        )
        was_truncated(response, "content_brief")
        payload = json.loads(strip_code_fences(response.content[0].text))
        title = str(payload["title"]).strip()
        angle = str(payload["angle"]).strip()
        outline = [str(item).strip() for item in payload["outline"] if str(item).strip()]
        if not title or not angle or not outline:
            raise ValueError("brief missing required fields")
    except Exception as exc:
        logger.warning(
            "content_brief_generation_failed",
            client_id=str(client.id),
            result_id=str(result.id),
            error=str(exc),
        )
        return None

    brief = (
        db.query(ContentBrief)
        .filter(ContentBrief.scan_query_result_id == result.id)
        .first()
    )
    if brief is None:
        brief = ContentBrief(client_id=client.id, scan_query_result_id=result.id)
        db.add(brief)
    brief.platform = result.platform
    brief.query_text = result.query_text
    brief.competitors_seen = competitors_seen
    brief.title = title
    brief.angle = angle
    brief.outline = outline
    brief.generated_at = utcnow()

    db.add(ActivityLog(
        client_id=client.id,
        event_type="brief_generated",
        note=f"Content brief generated for query: {result.query_text[:100]}",
    ))
    db.commit()
    db.refresh(brief)
    return brief
