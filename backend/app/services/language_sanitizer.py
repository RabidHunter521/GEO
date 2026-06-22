# backend/app/services/language_sanitizer.py
"""CLAUDE.md §2 vocabulary sanitizer — shared across all client-facing surfaces.

Import this instead of duplicating the forbidden-word list in each service.
The ordered list must stay in this module; never duplicate it elsewhere.
"""
import re

# Ordered list of (regex, replacement) pairs.
# Ordering matters: "not mentioned" / "uncited" must precede "mentioned" / "cited"
# so the negative forms are caught before the positive ones.
FORBIDDEN_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bnot mentioned\b", "not seen by AI"),
    (r"\buncited\b", "not seen by AI"),
    (r"\bmentioned\b", "seen by AI"),
    (r"\bcited\b", "seen by AI"),
    (r"\bcitation rate\b", "visibility frequency"),
    (r"\branking position\b", "AI Search Ranking"),
    (r"\bvisibility gap\b", "Your competitors are winning here"),
    (r"\bfirst mentioned\b", "first seen by AI"),
]


def sanitize_text(text: str | None) -> str:
    """Apply all §2 vocabulary replacements to a string.

    Handles None safely (returns ""). Never raises.
    """
    if not text:
        return "" if text is None else text
    try:
        for pattern, repl in FORBIDDEN_REPLACEMENTS:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    except Exception:
        pass  # never raise — caller gets best-effort sanitized string
    return text


def sanitize_bullets(bullets: list[str]) -> list[str]:
    """Apply sanitize_text to each bullet, strip whitespace, drop empties.

    Mirrors the original assessment_service.sanitize_bullets behaviour exactly.
    Never raises.
    """
    cleaned: list[str] = []
    for raw in bullets:
        text = sanitize_text(str(raw).strip())
        if text:
            cleaned.append(text)
    return cleaned
