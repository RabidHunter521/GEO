# backend/app/services/position_extraction.py
"""Extract a brand's rank position from a list-style AI response.

Used for `recommendation` and `local` queries where the AI answer is often an
ordered list ("1. Company A, 2. Company B, ..."). Returns the 1-based position
of the brand, or None when the response is not a ranked list or the brand is
absent. Additive to the binary brand_detected — never replaces it.
"""
import re
import uuid

from app.services.claude_client import MODEL, anthropic_client
from app.services.cost_tracker import record_llm_call


def extract_position(
    response_text: str, brand_name: str, client_id: uuid.UUID | None = None
) -> int | None:
    if not response_text:
        return None

    prompt = f"""An AI assistant was asked to recommend businesses. Below is its answer.

Brand to locate: "{brand_name}"

AI answer:
\"\"\"
{response_text[:4000]}
\"\"\"

If the answer presents businesses as a ranked or ordered list and "{brand_name}" appears in it,
reply with ONLY the 1-based position number (e.g. 3).
If the answer is not a ranked list, or "{brand_name}" is not in the list, reply with ONLY: none

Reply with a single number or the word none. Nothing else."""

    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    # db omitted on purpose: this runs in per-platform worker threads, so it must
    # not write through a shared session — record_llm_call opens its own.
    record_llm_call(
        service="position_extraction", model=MODEL, response=response, client_id=client_id
    )
    raw = response.content[0].text.strip().lower()
    if raw.startswith("none"):
        return None
    # Take the FIRST run of digits only. Joining every digit would turn a reply
    # like "3 (out of 10)" into 310; the first integer token is the position.
    match = re.search(r"\d+", raw)
    if not match:
        return None
    position = int(match.group())
    return position if position > 0 else None
