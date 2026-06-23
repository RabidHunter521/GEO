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

logger = structlog.get_logger()

# USD per token. Update when a provider changes published pricing.
#
# NOTE: the scan-platform rates below (gpt-5-mini, sonar, gemini-2.5-flash-lite)
# are best-effort placeholders pending confirmation against each provider's
# current price sheet — set them to your actual rates. They are intentionally
# nonzero so scan spend is no longer logged as $0 (see P1-4). Token *counts* are
# always exact; only this USD multiplier needs confirming. These rates also do
# NOT include per-request web-search / grounding surcharges, which several of
# these models bill separately on top of tokens.
_TOKEN_COST: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 2.50 / 1_000_000},
    "claude-sonnet-4-6":         {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    # ── Scan platforms (CONFIRM RATES) ───────────────────────────────────────
    "gpt-5-mini":                {"input": 0.25 / 1_000_000, "output": 2.00 / 1_000_000},
    "sonar":                     {"input": 1.00 / 1_000_000, "output": 1.00 / 1_000_000},
    "gemini-2.5-flash-lite":     {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    rates = _TOKEN_COST.get(model, {"input": 0.0, "output": 0.0})
    total = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
    return Decimal(str(round(total, 6)))


def record_llm_usage(
    *,
    service: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    client_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    """Log one LLM API call from raw token counts. Never raises.

    Use this for providers whose response shape differs from Anthropic's (the
    scan platforms: OpenAI, Perplexity, Gemini), where the caller has already
    extracted token usage. record_llm_call() delegates here for Anthropic.
    """
    try:
        cost = _compute_cost(model, input_tokens, output_tokens)
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
        client_id=client_id,
        db=db,
    )
