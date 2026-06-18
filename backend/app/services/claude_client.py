# backend/app/services/claude_client.py
"""Shared Anthropic (Claude) client helpers used across services."""
import re

import anthropic

from app.core.config import settings

MODEL = "claude-haiku-4-5-20251001"

# Used for higher-stakes prose (e.g. monthly report narratives) where writing
# quality matters more than per-call cost — call volume is low (1/report).
MODEL_NARRATIVE = "claude-sonnet-4-6"


# Bound a single Claude call so a hung request can't pin a Celery worker. Calls
# happen inside the scan/report flows; without this the SDK has no overall
# deadline. SDK retries (default) are kept — they cover transient 5xx/timeouts.
_CLAUDE_TIMEOUT_SECONDS = 60.0


def anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=_CLAUDE_TIMEOUT_SECONDS,
    )


def strip_code_fences(text: str) -> str:
    """Remove ```json or ``` code fences Claude sometimes adds despite instructions."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()
