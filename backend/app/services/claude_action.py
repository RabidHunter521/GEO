import anthropic
from app.core.config import settings
from app.core.constants import SCORE_BANDS, DIGEST_STATIC_TIPS
from app.models.client import Client


_MODEL = "claude-haiku-4-5-20251001"


def get_digest_action(
    client: Client,
    current_ai_citability: float,
    prev_ai_citability: float | None,
) -> str:
    score_change = (
        abs(current_ai_citability - prev_ai_citability)
        if prev_ai_citability is not None
        else 0.0
    )
    if score_change >= 5.0:
        try:
            return _generate_claude_action(client, current_ai_citability, prev_ai_citability)
        except Exception:
            pass
    return DIGEST_STATIC_TIPS[_score_band(current_ai_citability)]


def _score_band(score: float) -> str:
    for band, (lo, hi) in SCORE_BANDS.items():
        if lo <= score <= hi:
            return band
    return "low"


def _generate_claude_action(
    client: Client,
    current: float,
    prev: float | None,
) -> str:
    direction = "increased" if (prev is not None and current > prev) else "decreased"
    prompt = (
        f"You are a concise AI visibility advisor. "
        f"A business called '{client.name}' in the {client.industry} industry "
        f"had their AI visibility frequency {direction} "
        f"from {prev:.1f}% to {current:.1f}% this week. "
        f"Write exactly one sentence (under 20 words) recommending one specific action "
        f"they can take to improve or maintain their AI visibility. "
        f"Be direct. Do not use 'consider', 'you might', or 'perhaps'."
    )
    ai_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = ai_client.messages.create(
        model=_MODEL,
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
