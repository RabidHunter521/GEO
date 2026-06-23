# backend/tests/test_budget_service.py
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.llm_call_log import LlmCallLog
from app.services import budget_service


def _log(db, client_id, cost, days_ago=0):
    row = LlmCallLog(
        client_id=client_id,
        service="scan_gemini",
        prompt_version="v1",
        model="gemini-2.5-flash-lite",
        input_tokens=1,
        output_tokens=1,
        cost_usd=Decimal(str(cost)),
        called_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    db.add(row)
    db.commit()
    return row


def test_client_spend_last_30d_sums_only_recent(db):
    cid = uuid.uuid4()
    _log(db, cid, 5.00, days_ago=0)
    _log(db, cid, 2.00, days_ago=10)
    _log(db, cid, 99.00, days_ago=40)  # outside the 30-day window

    assert budget_service.client_spend_last_30d(cid, db) == Decimal("7.00")


def test_client_spend_is_scoped_to_client(db):
    a, b = uuid.uuid4(), uuid.uuid4()
    _log(db, a, 5.00)
    _log(db, b, 9.00)

    assert budget_service.client_spend_last_30d(a, db) == Decimal("5.00")


def test_global_spend_today_sums_all_clients(db):
    _log(db, uuid.uuid4(), 5.00, days_ago=0)
    _log(db, uuid.uuid4(), 4.00, days_ago=0)
    _log(db, uuid.uuid4(), 50.00, days_ago=2)  # not today

    assert budget_service.global_spend_today(db) == Decimal("9.00")


def test_check_budget_ok_when_under_caps(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 20.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 50.0)
    cid = uuid.uuid4()
    _log(db, cid, 3.00)

    status = budget_service.check_budget(cid, db)

    assert status.ok is True
    assert status.reason is None


def test_check_budget_blocks_on_client_cap(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 4.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 1000.0)
    cid = uuid.uuid4()
    _log(db, cid, 5.00)

    status = budget_service.check_budget(cid, db)

    assert status.ok is False
    assert "client" in status.reason.lower()


def test_check_budget_blocks_on_global_cap(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 1000.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 8.0)
    _log(db, uuid.uuid4(), 5.00)
    _log(db, uuid.uuid4(), 5.00)

    status = budget_service.check_budget(uuid.uuid4(), db)

    assert status.ok is False
    assert "daily" in status.reason.lower()


def test_check_budget_cap_of_zero_disables_check(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 0.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 0.0)
    cid = uuid.uuid4()
    _log(db, cid, 9999.00)

    assert budget_service.check_budget(cid, db).ok is True
