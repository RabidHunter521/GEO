"""Deterministic, client-specific fallback tip for the weekly digest.

Fires when the Claude action is gated off (< ±5pt AI-citability move) or fails.
Priority ladder — first rung whose data actually exists wins; no rung may state
a specific the data doesn't back (no invented evidence), and no LLM is called.
"""
from app.core.constants import DIGEST_STATIC_TIPS
from app.models.client import Client
from app.services.scoring_service import get_score_band

# Rung 3: one deterministic sentence per weakest dimension. Keys mirror the
# dimension naming in prompts/digest.py.
_DIMENSION_TIPS = {
    "brand authority": (
        "Your brand authority is your weakest area — a steady stream of Google "
        "reviews is the fastest public evidence AI models pick up on."
    ),
    "content quality": (
        "Your content quality is your weakest area — publishing one detailed "
        "service page that answers real customer questions moves it most."
    ),
}


def _battle_tip(battle) -> str:
    # No claim about score movement here: this tip also fires when the Claude
    # action fails on a big move, so it must stay true in both cases.
    return (
        f'The fastest path to moving your score: "{battle.query_text}" — '
        f'{battle.rival_name} is currently the one seen by AI there.'
    )


def select_digest_tip(client: Client, headline_battle, current_ai_citability: float | None) -> str:
    # Rung 1 — the client's live lost battle (already computed for the digest).
    if headline_battle is not None:
        return _battle_tip(headline_battle)

    # Rung 2 — unverified toolkit files, named specifically.
    if not client.technical_foundations_verified:
        return (
            "Your llms.txt isn't verified live yet — publishing it is the "
            "quickest visibility gain available this week."
        )
    if not client.structured_data_verified:
        return (
            "Your structured data (schema.json) isn't verified live yet — "
            "adding it helps AI models understand exactly what you offer."
        )

    # Rung 3 — weakest assisted dimension, deterministic template.
    if current_ai_citability is not None:
        dims = {
            "brand authority": float(client.brand_authority_score),
            "content quality": float(client.content_quality_score),
        }
        weakest = min(dims, key=dims.get)
        if dims[weakest] < current_ai_citability:
            return _DIMENSION_TIPS[weakest]
        # Citability itself is the weakest — the battle rung would normally
        # cover this; without one, fall through to the band tip.
        return DIGEST_STATIC_TIPS[get_score_band(current_ai_citability)[0]]

    # Rung 4 — band floor (no scan basis at all).
    return DIGEST_STATIC_TIPS[get_score_band(0.0)[0]]
