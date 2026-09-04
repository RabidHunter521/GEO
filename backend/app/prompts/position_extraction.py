# backend/app/prompts/position_extraction.py
"""Prompt template for rank-position extraction from a list-style AI answer.

Extracted from position_extraction_service, which held it inline — the second
of the two legacy inline prompts (see content_brief.py for the first). Being
here means it now carries a registered version, so its cost rows stop recording
"unknown".

No LANGUAGE_RULES here on purpose: the model's entire output is a bare integer
or the word "none", parsed by the caller and never surfaced to a client.
"""

# v1: extracted verbatim from position_extraction_service. The wording is
# unchanged — this prompt feeds AI Search Ranking, so any edit shifts scores
# and must bump this version.
VERSION = "v1"

# The answer is truncated before interpolation: positions live at the top of a
# ranked list, and an unbounded response would blow past the 8-token reply.
_MAX_ANSWER_CHARS = 4000


def build_position_extraction(response_text: str, brand_name: str) -> str:
    return f"""An AI assistant was asked to recommend businesses. Below is its answer.

Brand to locate: "{brand_name}"

AI answer:
\"\"\"
{response_text[:_MAX_ANSWER_CHARS]}
\"\"\"

If the answer presents businesses as a ranked or ordered list and "{brand_name}" appears in it,
reply with ONLY the 1-based position number (e.g. 3).
If the answer is not a ranked list, or "{brand_name}" is not in the list, reply with ONLY: none

Reply with a single number or the word none. Nothing else."""
