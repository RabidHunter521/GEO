# backend/app/services/budget_service.py
"""Spend guardrails read from the llm_call_logs ledger.

Scans are the dominant cost driver, so before one is triggered we check rolling
spend against two configurable caps (per-client 30-day, global daily). Over a
cap the trigger is hard-blocked and the admin alerted — the runaway-cost brake
the cost ledger was missing.

Caps come from settings and are env-configurable; a cap of 0 disables it.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.llm_call_log import LlmCallLog


@dataclass(frozen=True)
class BudgetStatus:
    """Result of a pre-scan budget check. reason is a human-readable block
    message when ok is False, else None."""

    ok: bool
    reason: str | None
    client_spend: Decimal
    global_spend: Decimal
    client_cap: float
    global_cap: float


def _now_naive() -> datetime:
    # called_at is stored as naive UTC (see LlmCallLog); compare in the same frame.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sum(db: Session, *filters) -> Decimal:
    return db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0)).filter(*filters).scalar() or Decimal("0")


def client_spend_last_30d(client_id: uuid.UUID, db: Session) -> Decimal:
    since = _now_naive() - timedelta(days=30)
    return _sum(db, LlmCallLog.client_id == client_id, LlmCallLog.called_at >= since)


def global_spend_today(db: Session) -> Decimal:
    start = _now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    return _sum(db, LlmCallLog.called_at >= start)


def check_budget(client_id: uuid.UUID, db: Session) -> BudgetStatus:
    """Check both caps. Global is evaluated first (the broader protection)."""
    client_cap = settings.BUDGET_CLIENT_MONTHLY_USD
    global_cap = settings.BUDGET_GLOBAL_DAILY_USD
    client_spend = client_spend_last_30d(client_id, db)
    global_spend = global_spend_today(db)

    reason: str | None = None
    if global_cap > 0 and global_spend >= Decimal(str(global_cap)):
        reason = (
            f"Global daily spend cap reached "
            f"(${global_spend:.2f} of ${global_cap:.2f})."
        )
    elif client_cap > 0 and client_spend >= Decimal(str(client_cap)):
        reason = (
            f"Client 30-day spend cap reached "
            f"(${client_spend:.2f} of ${client_cap:.2f})."
        )

    return BudgetStatus(
        ok=reason is None,
        reason=reason,
        client_spend=client_spend,
        global_spend=global_spend,
        client_cap=client_cap,
        global_cap=global_cap,
    )
