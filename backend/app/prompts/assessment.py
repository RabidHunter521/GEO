# backend/app/prompts/assessment.py
"""Prompt templates for Claude-assisted dimension assessment.

Condensed from the geo-brand-mentions (Brand Authority) and geo-content /
E-E-A-T (Content Quality) rubrics. Each prompt asks Claude to assess the
client's PUBLIC web/brand footprint and return a strict JSON contract.
"""
from app.models.client import Client
from app.core.constants import DIMENSION_BRAND_AUTHORITY, DIMENSION_CONTENT_QUALITY

BRAND_AUTHORITY_VERSION = "v1"
CONTENT_QUALITY_VERSION = "v1"

_LANGUAGE_RULES = (
    'Never use the words "citation", "cited", "mentioned", "citation rate", '
    '"ranking position", or "visibility gap". Use "seen by AI", "visibility '
    'frequency", and "AI Search Ranking" instead.'
)

_JSON_CONTRACT = (
    'Output ONLY valid JSON, no code fences, exactly:\n'
    '{"score": <integer 0-100>, "bullets": ["3-5 short plain-English evidence '
    'points a non-technical client would understand"], "narrative": "2-3 '
    'sentence internal rationale"}'
)


def _location(client: Client) -> str:
    return ", ".join(p for p in (client.city, client.state, client.country) if p)


def _brand_authority_prompt(client: Client) -> str:
    loc = _location(client)
    return f"""You assess the BRAND AUTHORITY of a {client.industry} business called {client.name}{f" based in {loc}" if loc else ""} for AI search visibility.
Website: {client.website}. Business context: {client.description or "n/a"}.

Brand Authority measures how strongly AI models recognise this brand as a real, trusted entity, based on PUBLIC signals an outsider could verify:
- Presence and engagement on high-AI-weight platforms (YouTube, Reddit, Wikipedia/Wikidata, LinkedIn).
- Third-party reviews and directory listings (Google, G2, Trustpilot, industry directories).
- Branded search demand and consistent name/usage across the web.

Score 0-100 where 80-100 = a widely-recognised authority, 50-64 = present but thin, 0-34 = almost no public footprint.
Each bullet must state an observable, public fact (e.g. "Listed on Google with 40+ reviews at 4.6 stars"), never an internal metric.
{_LANGUAGE_RULES}
{_JSON_CONTRACT}"""


def _content_quality_prompt(client: Client) -> str:
    loc = _location(client)
    return f"""You assess the CONTENT QUALITY (E-E-A-T) of a {client.industry} business called {client.name}{f" based in {loc}" if loc else ""} for AI search visibility.
Website: {client.website}. Business context: {client.description or "n/a"}.

Content Quality measures whether the website's content demonstrates Experience, Expertise, Authoritativeness, and Trustworthiness, and is structured so AI can extract and reuse it:
- Visible author credentials / bios; first-hand experience and original data.
- Depth, accurate use of industry terminology, references to external sources.
- Clear structure (headings, FAQs), freshness, and trust signals (contact, policies).

Score 0-100 where 80-100 = strong, well-structured expert content, 50-64 = adequate but shallow, 0-34 = thin or generic.
Each bullet must state an observable, public fact (e.g. "Author bios with credentials on all blog posts"), never an internal metric.
{_LANGUAGE_RULES}
{_JSON_CONTRACT}"""


_BUILDERS = {
    DIMENSION_BRAND_AUTHORITY: _brand_authority_prompt,
    DIMENSION_CONTENT_QUALITY: _content_quality_prompt,
}


def build_assessment_prompt(client: Client, dimension: str) -> str:
    if dimension not in _BUILDERS:
        raise ValueError(f"unknown dimension: {dimension}")
    return _BUILDERS[dimension](client)
