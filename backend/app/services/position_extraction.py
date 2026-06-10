# backend/app/services/position_extraction.py
"""Extract a brand's rank position from a list-style AI response.

Used for `recommendation` and `local` queries where the AI answer is often an
ordered list ("1. Company A, 2. Company B, ..."). Returns the 1-based position
of the brand, or None when the response is not a ranked list or the brand is
absent. Additive to the binary brand_detected — never replaces it.
"""
from app.services.claude_client import MODEL, anthropic_client


def extract_position(response_text: str, brand_name: str) -> int | None:
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
    raw = response.content[0].text.strip().lower()
    if raw.startswith("none"):
        return None
    # pull the first integer out of the reply, ignore anything else
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return None
    position = int(digits)
    return position if position > 0 else None
