# backend/app/prompts/content_roadmap.py
"""Prompt templates for the 90-day content roadmap generator."""
from app.models.client import Client

ROADMAP_VERSION = "v1"
ARTICLE_VERSION = "v2"

PLAN_WEEKS = 12  # 90-day plan == 12 weekly content pieces


def build_roadmap(client: Client, queries: list[dict]) -> str:
    location = ", ".join(p for p in (client.city, client.state, getattr(client, "country", None)) if p)
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

Build a prioritized 90-day content roadmap to make AI assistants start seeing {client.name} for these questions. Plan it as exactly {PLAN_WEEKS} weekly content pieces — one piece per week, week 1 through week {PLAN_WEEKS}, highest-impact first. Produce exactly {PLAN_WEEKS} items.
For each item:
- week: an integer from 1 to {PLAN_WEEKS} (each week appears exactly once)
- theme: the topic cluster it addresses
- priority: "high", "medium", or "low"
- target_queries: the exact question(s) from the list above this item helps win
- competitors_winning: competitor names currently seen for those questions (may be empty)
- content_type: e.g. "Blog post", "Comparison page", "FAQ page", "Location page"
- suggested_title: a specific, publish-ready title
- rationale: 1 sentence on why this wins the questions
Never use the words "citation", "cited", "mentioned", "ranking position", "outrank", "outranks", or "visibility gap" — use "seen by AI", "AI Search Ranking", and "Your competitors are winning here" instead.
Output ONLY valid JSON, no code fences, exactly:
{{"roadmap": [{{"week": 1, "theme": "string", "priority": "high", "target_queries": ["string"], "competitors_winning": ["string"], "content_type": "string", "suggested_title": "string", "rationale": "string"}}]}}"""


def build_article(client: Client, item: dict) -> str:
    location = ", ".join(p for p in (client.city, client.state, getattr(client, "country", None)) if p)
    queries = item.get("target_queries") or []
    query_lines = "\n".join(f'- "{q}"' for q in queries) or "- (general brand visibility)"
    return f"""You are a GEO (Generative Engine Optimization) content writer for a {client.industry} business called {client.name}{f" based in {location}" if location else ""}.
Business context: {client.description or "n/a"}. Target audience: {client.target_audience or "n/a"}.

Write the full, publish-ready draft of this content piece:
- Title: {item.get("suggested_title", "")}
- Format: {item.get("content_type", "Blog post")}
- Topic cluster: {item.get("theme", "")}
- It should help this business get seen by AI assistants for these questions:
{query_lines}

Requirements:
- Write the complete article in Markdown (use ## headings, short paragraphs, bullet lists where useful).
- Aim for 600-900 words, genuinely useful and specific to this business and its audience.
- Naturally include the business name and the kind of language a buyer would use when asking AI assistants the questions above.
- Be accurate and concrete; do not invent fake statistics, awards, or quotes.
- Never use the words "citation", "cited", "mentioned", "ranking position", "outrank", "outranks", or "visibility gap".

After the article body, append exactly this metadata block with no extra blank lines between them:

---
SEO_TITLE: [browser tab/search snippet title — under 60 characters, may differ from the H1]
META_DESC: [meta description — 140–155 characters, ends with a natural call to action]
SLUG: [url-friendly slug — lowercase, hyphens only, under 60 characters, omit stop words]
INTERNAL_LINKS: [2-3 related topics already on this site that this article could link to]

No preamble. No code fences. Article body first, metadata block last."""
