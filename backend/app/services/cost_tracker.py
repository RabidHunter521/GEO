# backend/app/services/cost_tracker.py
"""Per-call LLM cost tracking.

Call record_llm_call() immediately after every anthropic_client().messages.create().
It reads token usage from the response, computes USD cost, and writes to llm_call_logs.

Session handling:
  - db provided  → adds to the session; caller manages commit (no extra connection).
  - db omitted   → opens its own SessionLocal and commits immediately (fire-and-forget).

Failures are caught and logged — never propagate to the calling service.
"""
import uuid
from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from app.models.llm_call_log import LlmCallLog
from app.prompts.registry import get_version
from app.services.claude_client import web_search_requests

logger = structlog.get_logger()

# USD per token. Update when a provider changes published pricing.
#
# Verified 2026-09-04 against each provider's published price sheet:
#   Anthropic   platform.claude.com/docs/en/about-claude/pricing
#   OpenAI      developers.openai.com/api/docs/pricing
#   Perplexity  docs.perplexity.ai/getting-started/pricing
#   Google      ai.google.dev/gemini-api/docs/pricing
# Token *counts* are always exact; these are only the USD multipliers.
_TOKEN_COST: dict[str, dict[str, float]] = {
    # Was $0.80/$2.50 — those are Claude Haiku *3.5* rates, carried over when
    # the model was upgraded. Haiku 4.5 bills $1/$5, so every internal Haiku
    # call (the majority of them) under-reported output spend by 2x.
    "claude-haiku-4-5-20251001": {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    "claude-sonnet-4-6":         {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    # ── Scan platforms ───────────────────────────────────────────────────────
    "gpt-5-mini":                {"input": 0.25 / 1_000_000, "output": 2.00 / 1_000_000},
    # Was $1.00 output — sonar bills $1 in / $2.50 out.
    "sonar":                     {"input": 1.00 / 1_000_000, "output": 2.50 / 1_000_000},
    "gemini-2.5-flash-lite":     {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
}

# USD per web search / grounded request, billed ON TOP of tokens. Every scan
# query runs with search enabled, so this is not an edge case: for Gemini the
# surcharge dwarfs the tokens (~$0.035 vs ~$0.0004 a query), and omitting it
# under-reported scan spend by roughly two orders of magnitude.
#
# Two caveats keep these figures honest rather than exact:
#   - Gemini's first 1,500 grounded prompts/day are free (allowance shared with
#     Flash), so its charge here is an upper bound on a low-volume day.
#   - Perplexity's $5/1k is the low-context tier, which is what we send today;
#     medium/high context bill $8/$12 per 1k.
_SEARCH_COST: dict[str, float] = {
    "claude-haiku-4-5-20251001": 10.00 / 1_000,  # Anthropic web_search, per search
    "claude-sonnet-4-6":         10.00 / 1_000,
    "gpt-5-mini":                10.00 / 1_000,  # OpenAI web_search, per tool call
    "sonar":                      5.00 / 1_000,  # Perplexity, per request
    "gemini-2.5-flash-lite":     35.00 / 1_000,  # Google Search grounding, per prompt
}


def _compute_cost(
    model: str, input_tokens: int, output_tokens: int, search_count: int = 0
) -> Decimal:
    rates = _TOKEN_COST.get(model)
    if rates is None:
        # A renamed or newly added model must not make spend quietly vanish:
        # the row is still written (cost logging never blocks a scan), but the
        # gap is loud in the logs instead of silently costing $0.
        logger.warning("llm_cost_model_unpriced", model=model)
        rates = {"input": 0.0, "output": 0.0}
    total = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
    total += search_count * _SEARCH_COST.get(model, 0.0)
    return Decimal(str(round(total, 6)))


def record_llm_usage(
    *,
    service: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    search_count: int = 0,
    client_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    """Log one LLM API call from raw token counts. Never raises.

    Use this for providers whose response shape differs from Anthropic's (the
    scan platforms: OpenAI, Perplexity, Gemini), where the caller has already
    extracted token usage. record_llm_call() delegates here for Anthropic.

    search_count is the number of billable web searches / grounded requests the
    call made, which providers charge per request on top of tokens.
    """
    try:
        cost = _compute_cost(model, input_tokens, output_tokens, search_count)
        entry = LlmCallLog(
            client_id=client_id,
            service=service,
            prompt_version=get_version(service),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        if db is not None:
            db.add(entry)
        else:
            from app.core.database import SessionLocal
            with SessionLocal() as session:
                session.add(entry)
                session.commit()
    except Exception as exc:
        logger.warning(
            "cost_tracking_failed",
            service=service,
            client_id=str(client_id),
            error=str(exc),
        )


def record_llm_call(
    *,
    service: str,
    model: str,
    response,
    client_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    """Log one Anthropic API call, reading usage off the response. Never raises."""
    try:
        usage = response.usage
        input_tokens, output_tokens = usage.input_tokens, usage.output_tokens
    except Exception as exc:
        logger.warning(
            "cost_tracking_failed",
            service=service,
            client_id=str(client_id),
            error=str(exc),
        )
        return
    record_llm_usage(
        service=service,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        # Exact count off the response, so non-search calls are charged nothing.
        search_count=web_search_requests(response),
        client_id=client_id,
        db=db,
    )
