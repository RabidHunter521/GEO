from sqlalchemy.orm import Session

from app.core.constants import SCORE_BANDS, DIGEST_STATIC_TIPS
from app.models.client import Client
from app.prompts.digest import build_action
from app.services.claude_client import MODEL, anthropic_client
from app.services.cost_tracker import record_llm_call


def get_digest_action(
    client: Client,
    current_ai_citability: float,
    prev_ai_citability: float | None,
    db: Session | None = None,
) -> str:
    score_change = (
        abs(current_ai_citability - prev_ai_citability)
        if prev_ai_citability is not None
        else 0.0
    )
    if score_change >= 5.0:
        try:
            return _generate_claude_action(client, current_ai_citability, prev_ai_citability, db)
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
    db: Session | None = None,
) -> str:
    prompt = build_action(client, current, prev)
    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    record_llm_call(
        service="digest_action",
        model=MODEL,
        response=response,
        client_id=client.id,
        db=db,
    )
    return response.content[0].text.strip()
