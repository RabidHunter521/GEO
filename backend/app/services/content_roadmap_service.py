"""90-day content roadmap generator.

Turns the queries a client is losing to competitors (win/loss "lost"/"open"
entries from the latest scan) into a prioritized, time-phased content plan via
one Claude call. Reuses compute_win_loss so it stays in sync with the
admin win/loss board. Generated here (admin-triggered), but roadmap_json is
also read verbatim by the client-view /roadmap endpoint — every field is
client-facing and must follow CLAUDE.md §2 language rules.
"""
import json

import structlog
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.models.client import Client
from app.prompts.content_roadmap import PLAN_WEEKS, build_article, build_roadmap
from app.services.claude_client import MODEL_NARRATIVE, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_text
from app.services.win_loss_service import compute_win_loss

logger = structlog.get_logger()

_MAX_TOKENS = 4096
_ARTICLE_MAX_TOKENS = 3500
_MAX_QUERIES = 24  # cap prompt size; most-recent lost/open queries are enough


def _lost_queries(client_id, db: Session) -> list[dict]:
    """The client's lost/open neutral-intent queries from the latest scan."""
    win_loss = compute_win_loss(client_id, db)
    return [
        {
            "query_text": entry.query_text,
            "platform": PLATFORM_LABELS.get(entry.platform, entry.platform),
            "category": entry.category,
            "competitors_winning": entry.competitors_seen,
        }
        for entry in win_loss.entries
        if entry.outcome in ("lost", "open")
    ]


def generate_roadmap(client: Client, db: Session) -> dict:
    """Returns {"roadmap_json": [...], "source_query_count": int}.

    No lost/open queries → empty roadmap (no Claude call). Raises on Claude
    failure / unparseable output so the Celery task marks the run failed."""
    queries = _lost_queries(client.id, db)
    if not queries:
        return {"roadmap_json": [], "source_query_count": 0}

    prompt = build_roadmap(client, queries[:_MAX_QUERIES])
    response = anthropic_client().messages.create(
        model=MODEL_NARRATIVE,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    record_llm_call(
        service="content_roadmap",
        model=MODEL_NARRATIVE,
        response=response,
        client_id=client.id,
        db=db,
    )
    payload = json.loads(strip_code_fences(response.content[0].text))
    items = payload["roadmap"] if isinstance(payload, dict) else payload

    roadmap_json = []
    for fallback_week, item in enumerate(items, start=1):
        title = str(item.get("suggested_title", "")).strip()
        theme = str(item.get("theme", "")).strip()
        if not title or not theme:
            continue
        week = int(item.get("week", fallback_week) or fallback_week)
        week = max(1, min(PLAN_WEEKS, week))
        roadmap_json.append({
            "week": week,
            "theme": theme,
            "priority": str(item.get("priority", "medium")).strip().lower(),
            "target_queries": [str(q).strip() for q in item.get("target_queries", []) if str(q).strip()],
            "competitors_winning": [str(c).strip() for c in item.get("competitors_winning", []) if str(c).strip()],
            "content_type": str(item.get("content_type", "Blog post")).strip(),
            "suggested_title": title,
            "rationale": sanitize_text(str(item.get("rationale", "")).strip()),
            "article_content": None,
        })

    if not roadmap_json:
        raise ValueError("roadmap generation produced no valid items")

    return {"roadmap_json": roadmap_json, "source_query_count": len(queries)}


def generate_article_content(client: Client, item: dict) -> str:
    """Generate the full Markdown article draft for a single roadmap item.

    Raises on Claude failure / empty output so the caller can surface an error."""
    prompt = build_article(client, item)
    response = anthropic_client().messages.create(
        model=MODEL_NARRATIVE,
        max_tokens=_ARTICLE_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    record_llm_call(
        service="content_roadmap_article",
        model=MODEL_NARRATIVE,
        response=response,
        client_id=client.id,
    )
    content = strip_code_fences(response.content[0].text).strip()
    if not content:
        raise ValueError("article generation produced no content")
    return content
