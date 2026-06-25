# backend/app/prompts/digest.py
"""Prompt template for the weekly digest action tip."""
from app.models.client import Client

VERSION = "v2"


def build_action(client: Client, current: float, prev: float | None) -> str:
    if prev is not None and current > prev:
        direction = "increased"
    elif prev is not None and current < prev:
        direction = "decreased"
    else:
        direction = "held steady"

    prev_str = f"from {prev:.1f}% " if prev is not None else ""

    # Find the weakest scoring dimension so the tip targets the real gap.
    # technical_foundations and structured_data are verified booleans — treat
    # unverified as 0 so they surface as the weakest when the toolkit isn't set up.
    dimensions: dict[str, float] = {
        "AI visibility frequency": current,
        "brand authority": float(client.brand_authority_score),
        "content quality": float(client.content_quality_score),
        "technical foundations": 100.0 if client.technical_foundations_verified else 0.0,
        "structured data": 100.0 if client.structured_data_verified else 0.0,
    }
    weakest_dim, weakest_score = min(dimensions.items(), key=lambda x: x[1])

    return (
        f"You are a concise AI visibility advisor. "
        f"A {client.industry} business called '{client.name}' "
        f"had their AI visibility frequency {direction} {prev_str}to {current:.1f}% this week. "
        f"Their weakest area right now is {weakest_dim} ({weakest_score:.0f}/100). "
        f"Write exactly one sentence (under 30 words) recommending one specific, concrete action "
        f"targeting {weakest_dim} to improve their AI visibility. "
        f"Be direct. Do not use 'consider', 'you might', or 'perhaps'."
    )
