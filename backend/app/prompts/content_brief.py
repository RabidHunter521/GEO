# backend/app/prompts/content_brief.py
"""Prompt template for on-demand content briefs.

Extracted from content_brief_service, which held it inline — one of the two
legacy inline prompts. Being here means it now carries a registered version, so
its cost rows stop recording "unknown", and it shares LANGUAGE_RULES instead of
keeping a private copy that had already drifted from the canonical list.
"""
from app.core.constants import PLATFORM_LABELS
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult
from app.prompts.industry_pack import build_pack_context
from app.prompts.language import LANGUAGE_RULES

# v2: extracted from content_brief_service; shared LANGUAGE_RULES replaces this
# prompt's own shorter copy (it omitted "uncited", "first mentioned", "citation
# rate", "char offset" and "token count"); industry pack context added.
VERSION = "v2"


def build_content_brief(
    client: Client,
    result: ScanQueryResult,
    competitors_seen: list[str],
    pack=None,
    facts=(),
) -> str:
    location = ", ".join(p for p in (client.city, client.state, client.country) if p)
    competitor_line = (
        f"the answer included these competitors: {', '.join(competitors_seen)} — but "
        if competitors_seen
        else "no business stood out in the answer, and "
    )
    return f"""You are a GEO (Generative Engine Optimization) content strategist for a {client.industry} business called {client.name}{f" based in {location}" if location else ""}.
Business context: {client.description or "n/a"}. Target audience: {client.target_audience or "n/a"}.
{build_pack_context(client, pack, facts)}
When AI assistants were asked: "{result.query_text}" (platform: {PLATFORM_LABELS.get(result.platform, result.platform)}), {competitor_line}{client.name} was not yet seen by AI in that answer.

Create one content brief for a page or blog post designed to make AI assistants include {client.name} when answering this exact question.
- title: a specific, publish-ready page/post title using the industry and locality terms from the question.
- angle: 1-2 sentences on the unique angle that wins this question (what existing coverage is missing).
- outline: 4-7 plain-English section bullets (H2 level).
{LANGUAGE_RULES}
Output ONLY valid JSON, no code fences, exactly:
{{"title": "string", "angle": "string", "outline": ["string"]}}"""
