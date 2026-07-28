# backend/app/services/claude_client.py
"""Shared Anthropic (Claude) client helpers used across services."""
import re

import anthropic
import structlog

from app.core.config import settings

logger = structlog.get_logger()

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


def was_truncated(response, service: str) -> bool:
    """True when the model ran out of output budget mid-answer.

    A `max_tokens` stop is not the same failure as a malformed reply: the JSON
    is *valid so far* and simply ends early, so a plain json.loads error tells
    you nothing about the cause and the fix (raise max_tokens) is invisible.
    Log it distinctly at the call site so a truncated deliverable is
    diagnosable from the logs alone (prompt audit H4).
    """
    truncated = getattr(response, "stop_reason", None) == "max_tokens"
    if truncated:
        logger.warning("claude_response_truncated", service=service,
                       hint="raise max_tokens for this prompt")
    return truncated
