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

# USD per token. Update when Anthropic changes published pricing.
_TOKEN_COST: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 2.50 / 1_000_000},
    "claude-sonnet-4-6":         {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    rates = _TOKEN_COST.get(model, {"input": 0.0, "output": 0.0})
    total = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
    return Decimal(str(round(total, 6)))


def record_llm_call(
    *,
    service: str,
    model: str,
    response,
    client_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> None:
    """Log one LLM API call. Never raises."""
    try:
        usage = response.usage
        cost = _compute_cost(model, usage.input_tokens, usage.output_tokens)
        entry = LlmCallLog(
            client_id=client_id,
            service=service,
            prompt_version=get_version(service),
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
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
