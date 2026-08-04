# backend/tests/test_budget_service.py
import uuid
from datetime import timedelta
from decimal import Decimal

from app.models.client import Client
from app.models.llm_call_log import LlmCallLog
from app.services import budget_service
from app.core.time import utcnow


def _client(db, client_id):
    client = db.get(Client, client_id)
    if client is not None:
        return client

    client = Client(
        id=client_id,
        name="Acme",
        website="https://acme.com",
        industry="software",
    )
    db.add(client)
    db.commit()
    return client


def _log(db, client_id, cost, days_ago=0):
    if client_id is not None:
        _client(db, client_id)

    row = LlmCallLog(
        client_id=client_id,
        service="scan_gemini",
        prompt_version="v1",
        model="gemini-2.5-flash-lite",
        input_tokens=1,
        output_tokens=1,
        cost_usd=Decimal(str(cost)),
        called_at=utcnow() - timedelta(days=days_ago),
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


# ── remaining_budget_usd (query_sampling_service's planning input) ──────────

def test_remaining_budget_usd_is_none_when_both_caps_disabled(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 0.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 0.0)
    cid = uuid.uuid4()

    assert budget_service.remaining_budget_usd(cid, db) is None


def test_remaining_budget_usd_uses_tighter_of_the_two_caps(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 20.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 50.0)
    cid = uuid.uuid4()
    _log(db, cid, 15.00)  # client headroom: 5.00
    _log(db, uuid.uuid4(), 10.00)  # counts only toward the global cap: headroom 40.00

    assert budget_service.remaining_budget_usd(cid, db) == Decimal("5.00")


def test_remaining_budget_usd_floors_at_zero_when_already_over_cap(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 4.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 1000.0)
    cid = uuid.uuid4()
    _log(db, cid, 9.00)

    assert budget_service.remaining_budget_usd(cid, db) == Decimal("0")


def test_remaining_budget_usd_ignores_a_disabled_cap(db, monkeypatch):
    monkeypatch.setattr(budget_service.settings, "BUDGET_CLIENT_MONTHLY_USD", 0.0)
    monkeypatch.setattr(budget_service.settings, "BUDGET_GLOBAL_DAILY_USD", 50.0)
    cid = uuid.uuid4()
    _log(db, cid, 5.00)

    # Only the global cap is active: 50 - 5 = 45.
    assert budget_service.remaining_budget_usd(cid, db) == Decimal("45.00")
