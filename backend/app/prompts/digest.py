# backend/app/prompts/digest.py
"""Prompt template for the weekly digest action tip."""
from app.models.client import Client

VERSION = "v1"


def build_action(client: Client, current: float, prev: float | None) -> str:
    direction = "increased" if (prev is not None and current > prev) else "decreased"
    return (
        f"You are a concise AI visibility advisor. "
        f"A business called '{client.name}' in the {client.industry} industry "
        f"had their AI visibility frequency {direction} "
        f"from {prev:.1f}% to {current:.1f}% this week. "
        f"Write exactly one sentence (under 20 words) recommending one specific action "
        f"they can take to improve or maintain their AI visibility. "
        f"Be direct. Do not use 'consider', 'you might', or 'perhaps'."
    )
