# backend/app/services/content_brief_service.py
"""On-demand Claude content briefs for queries the client lost to competitors."""
import json
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.content_brief import ContentBrief
from app.models.scan_query_result import ScanQueryResult
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL

logger = structlog.get_logger()

_MAX_TOKENS = 1024


def _build_prompt(client: Client, result: ScanQueryResult, competitors_seen: list[str]) -> str:
    location = ", ".join(p for p in (client.city, client.state, client.country) if p)
    competitor_line = (
        f"the answer included these competitors: {', '.join(competitors_seen)} — but "
        if competitors_seen
        else "no business stood out in the answer, and "
    )
    return f"""You are a GEO (Generative Engine Optimization) content strategist for a {client.industry} business called {client.name}{f" based in {location}" if location else ""}.
Business context: {client.description or "n/a"}. Target audience: {client.target_audience or "n/a"}.

When AI assistants were asked: "{result.query_text}" (platform: {PLATFORM_LABELS.get(result.platform, result.platform)}), {competitor_line}{client.name} was not yet seen by AI in that answer.

Create one content brief for a page or blog post designed to make AI assistants include {client.name} when answering this exact question.
- title: a specific, publish-ready page/post title using the industry and locality terms from the question.
- angle: 1-2 sentences on the unique angle that wins this question (what existing coverage is missing).
- outline: 4-7 plain-English section bullets (H2 level).
Never use the words "citation", "cited", "mentioned", "ranking position", or "visibility gap" — use "seen by AI", "AI Search Ranking", and "Your competitors are winning here" instead.
Output ONLY valid JSON, no code fences, exactly:
{{"title": "string", "angle": "string", "outline": ["string"]}}"""


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
            messages=[{"role": "user", "content": _build_prompt(client, result, competitors_seen)}],
        )
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
    brief.generated_at = datetime.utcnow()

    db.add(ActivityLog(
        client_id=client.id,
        event_type="brief_generated",
        note=f"Content brief generated for query: {result.query_text[:100]}",
    ))
    db.commit()
    db.refresh(brief)
    return brief
