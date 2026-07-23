# backend/app/prompts/deliverables.py
"""Prompts for the three content deliverable generators (Content Studio).

Output is published under the CLIENT's name — every prompt forbids invented
facts, and the comparison prompt additionally enforces a fair tone. The
admin-review gate is mandatory, not decorative.
"""
from app.models.client import Client
from app.models.competitor import Competitor

FAQ_PACK_VERSION = "v1"
COMPARISON_PAGE_VERSION = "v1"
GLOSSARY_VERSION = "v1"

_LANGUAGE_RULES = (
    'Never use the words "citation", "cited", "mentioned", "citation rate", '
    '"ranking position", or "visibility gap" — say "seen by AI" and '
    '"visibility frequency" instead.'
)

_ENVELOPE_RULES = """Output ONLY valid JSON, no code fences, exactly:
{"title": "string", "body_md": "string"}
body_md is complete GitHub-flavoured Markdown, publish-ready."""


def _profile(client: Client) -> str:
    location = ", ".join(p for p in (client.city, client.state, client.country) if p)
    return f"""Business: {client.name} ({client.industry}{f", {location}" if location else ""})
Website: {client.website}
Description: {client.description or "n/a"}
Target audience: {client.target_audience or "n/a"}"""


def build_faq_pack(client: Client, lost_queries: list[str]) -> str:
    queries_block = (
        "\n".join(f"- {q}" for q in lost_queries)
        if lost_queries
        else "- (no scan data yet — infer typical customer questions from the profile)"
    )
    return f"""You are a GEO content writer. Create a publish-ready FAQ pack for this business.

{_profile(client)}

These are real questions people asked AI assistants where {client.name} was not yet seen by AI:
{queries_block}

Write 8-12 Q&A pairs:
- Questions phrased exactly the way a customer would ask an AI assistant.
- Each answer 2-4 sentences, specific to this business, naturally including the business \
name where it reads well. Ground every claim ONLY in the profile above — never invent \
prices, statistics, certifications, or services.
- Cover the lost questions above first, then round out with the most common questions for \
this industry.
- End body_md with a one-line note: "Tip: add this FAQ to your site together with FAQPage \
schema — the SeenBy toolkit generates it."
Format body_md as: H1 title, then "## Question" headings each followed by the answer paragraph.
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""


def build_comparison_page(client: Client, competitor: Competitor, evidence_lines: list[str]) -> str:
    evidence_block = (
        "\n".join(f"- {line}" for line in evidence_lines)
        if evidence_lines
        else "- (no head-to-head data yet)"
    )
    return f"""You are a GEO content writer. Draft a fair, factual comparison page: \
{client.name} vs {competitor.name}.

{_profile(client)}

Competitor: {competitor.name}{f" ({competitor.website})" if competitor.website else ""}

Head-to-head context from AI-assistant answers (admin evidence, do not quote directly):
{evidence_block}

Structure body_md exactly as:
1. H1: "{client.name} vs {competitor.name}: Which Is Right for You?"
2. A 2-3 sentence neutral intro.
3. "## At a glance" — a Markdown comparison table. Rows ONLY for factual aspects you can \
ground in the profile (services, location, audience). Where you don't know the \
competitor's side, write "Check their website" — NEVER invent competitor facts.
4. "## When {client.name} is the better fit" — grounded in the profile only.
5. "## When {competitor.name} may fit" — honest, respectful; no invented weaknesses.
6. "## Frequently asked questions" — 3-4 Q&As about choosing between them.

Hard rules: never disparage {competitor.name}; no invented facts or statistics for either \
business; no superlatives about {client.name} that are not in the profile above.
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""


def build_glossary(client: Client, query_texts: list[str]) -> str:
    queries_block = (
        "\n".join(f"- {q}" for q in query_texts[:40])
        if query_texts
        else "- (no scan data yet — use the industry's standard vocabulary)"
    )
    return f"""You are a GEO content writer. Create an industry glossary page for this business.

{_profile(client)}

Terms and phrasing appear in these real AI-assistant queries about this market:
{queries_block}

Write 15-20 glossary entries:
- Pick the terms a customer of this industry actually encounters (harvest candidates from \
the queries above, then fill with standard industry terms).
- Each entry: "## Term" heading, then ONE plain-English paragraph (2-4 sentences) a \
layperson understands. Definition sentences should start "X is …" — AI assistants quote \
that form directly.
- Where natural (at most 5 entries), relate the term to how {client.name} handles it — \
grounded only in the profile.
- Alphabetical order. H1: "{client.industry} Terms Explained".
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""
