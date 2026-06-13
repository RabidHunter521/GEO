"""90-day content roadmap generator.

Turns the queries a client is losing to competitors (win/loss "lost"/"open"
entries from the latest scan) into a prioritized, time-phased content plan via
one Claude call. Reuses compute_win_loss so it stays in sync with the
admin win/loss board. Admin-only — never surfaced through the client view.
"""
import json

import structlog
from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.models.client import Client
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL_NARRATIVE
from app.services.win_loss_service import compute_win_loss

logger = structlog.get_logger()

_MAX_TOKENS = 2048
_MAX_QUERIES = 24  # cap the prompt; the most recent lost/open queries are enough


def _lost_queries(client_id, db: Session) -> list[dict]:
    """The client's lost/open neutral-intent queries from the latest scan."""
    win_loss = compute_win_loss(client_id, db)
    out = []
    for entry in win_loss.entries:
        if entry.outcome in ("lost", "open"):
            out.append({
                "query_text": entry.query_text,
                "platform": PLATFORM_LABELS.get(entry.platform, entry.platform),
                "category": entry.category,
                "competitors_winning": entry.competitors_seen,
            })
    return out


def _build_prompt(client: Client, queries: list[dict]) -> str:
    location = ", ".join(p for p in (client.city, client.state, client.country) if p)
    query_lines = "\n".join(
        f'- "{q["query_text"]}" ({q["platform"]}, {q["category"]}; '
        + (f'competitors winning: {", ".join(q["competitors_winning"])}' if q["competitors_winning"] else "no one stands out")
        + ")"
        for q in queries
    )
    return f"""You are a GEO (Generative Engine Optimization) content strategist for a {client.industry} business called {client.name}{f" based in {location}" if location else ""}.
Business context: {client.description or "n/a"}. Target audience: {client.target_audience or "n/a"}.

These are the questions where AI assistants did NOT yet see {client.name}, and where competitors often are seen instead:
{query_lines}

Build a prioritized 90-day content roadmap to make AI assistants start seeing {client.name} for these questions. Group the work into 3 monthly blocks (month 1, 2, 3), highest-impact first. Produce 5-9 items total across the three months.
For each item:
- month: 1, 2, or 3
- theme: the topic cluster it addresses
- priority: "high", "medium", or "low"
- target_queries: the exact question(s) from the list above this item helps win
- competitors_winning: competitor names currently seen for those questions (may be empty)
- content_type: e.g. "Blog post", "Comparison page", "FAQ page", "Location page"
- suggested_title: a specific, publish-ready title
- rationale: 1 sentence on why this wins the questions
Never use the words "citation", "cited", "mentioned", "ranking position", or "visibility gap" — use "seen by AI", "AI Search Ranking", and "Your competitors are winning here" instead.
Output ONLY valid JSON, no code fences, exactly:
{{"roadmap": [{{"month": 1, "theme": "string", "priority": "high", "target_queries": ["string"], "competitors_winning": ["string"], "content_type": "string", "suggested_title": "string", "rationale": "string"}}]}}"""


def generate_roadmap(client: Client, db: Session) -> dict:
    """Returns {"roadmap_json": [...], "source_query_count": int}.

    No lost/open queries → empty roadmap (no Claude call). Raises on Claude
    failure / unparseable output so the Celery task marks the run failed."""
    queries = _lost_queries(client.id, db)
    if not queries:
        return {"roadmap_json": [], "source_query_count": 0}

    prompt = _build_prompt(client, queries[:_MAX_QUERIES])
    response = anthropic_client().messages.create(
        model=MODEL_NARRATIVE,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    payload = json.loads(strip_code_fences(response.content[0].text))
    items = payload["roadmap"] if isinstance(payload, dict) else payload

    roadmap_json = []
    for item in items:
        title = str(item.get("suggested_title", "")).strip()
        theme = str(item.get("theme", "")).strip()
        if not title or not theme:
            continue
        roadmap_json.append({
            "month": int(item.get("month", 1)),
            "theme": theme,
            "priority": str(item.get("priority", "medium")).strip().lower(),
            "target_queries": [str(q).strip() for q in item.get("target_queries", []) if str(q).strip()],
            "competitors_winning": [str(c).strip() for c in item.get("competitors_winning", []) if str(c).strip()],
            "content_type": str(item.get("content_type", "Blog post")).strip(),
            "suggested_title": title,
            "rationale": str(item.get("rationale", "")).strip(),
        })

    if not roadmap_json:
        raise ValueError("roadmap generation produced no valid items")

    return {"roadmap_json": roadmap_json, "source_query_count": len(queries)}
