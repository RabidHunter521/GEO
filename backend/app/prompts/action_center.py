# backend/app/prompts/action_center.py
"""Prompt template for the GEO Action Center."""
from app.models.client import Client
from app.core.constants import SCORE_BANDS, SCORE_WEIGHTS

VERSION = "v1"

DIMENSIONS = (
    "ai_citability",
    "brand_authority",
    "content_quality",
    "technical_foundations",
    "structured_data",
)

DIMENSION_LABELS = {
    "ai_citability":         "AI Citability",
    "brand_authority":       "Brand Authority",
    "content_quality":       "Content Quality",
    "technical_foundations": "Technical Foundations",
    "structured_data":       "Structured Data",
}


def build(
    client: Client,
    scores: dict[str, float],
    missing_topics: list[str],
    competitor_winning: bool,
) -> str:
    score_lines = []
    for dim in DIMENSIONS:
        score = scores[dim]
        band = next((name for name, (lo, hi) in SCORE_BANDS.items() if lo <= int(score) <= hi), "low")
        score_lines.append(
            f"- {DIMENSION_LABELS[dim]} ({dim}): {score:.0f}/100, weight {SCORE_WEIGHTS[dim] * 100:.0f}%, band: {band}"
        )

    context_lines = []
    if missing_topics:
        context_lines.append("Topics not yet covered on the website: " + ", ".join(missing_topics))
    if competitor_winning:
        context_lines.append("At least one competitor currently appears in AI answers more often than this business.")

    context_block = "\n".join(context_lines) if context_lines else "No additional context available."

    return f"""You are a GEO (Generative Engine Optimization) advisor for a {client.industry} business
called {client.name}. Their AI visibility score breaks down into 5 dimensions:

{chr(10).join(score_lines)}

Additional context:
{context_block}

Suggest 3-5 specific, practical actions this business could take to improve their AI visibility
score, prioritizing dimensions that are weakest and have the highest weight. For each action:
- action_text: one specific, plain-English sentence describing the action. Use phrases like
  "Your competitors are winning here" instead of "visibility gap", and never use the words
  "citation", "ranking position", "confidence", or "token".
- dimension: which one of {", ".join(DIMENSIONS)} this action primarily improves.
- closable_gap_fraction: your estimate (0.0 to 1.0) of how much of that dimension's remaining
  gap to 100 this single action could realistically close.

Output ONLY valid JSON, no code fences, in exactly this shape:
{{"actions": [{{"action_text": "string", "dimension": "string", "closable_gap_fraction": 0.0}}]}}"""
