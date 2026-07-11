# backend/tests/test_circuit_breaker.py

import pytest

from app.services import circuit_breaker as cb


class FakeRedis:
    """Minimal in-memory stand-in for the redis ops the breaker uses."""

    def __init__(self):
        self.store = {}

    def get(self, k):
        return self.store.get(k)

    def set(self, k, v, ex=None, nx=False):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    def incr(self, k):
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    def expire(self, k, seconds):
        return True

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


@pytest.fixture
def fake(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(cb, "_get_client", lambda: r)
    monkeypatch.setattr(cb.settings, "CIRCUIT_BREAKER_THRESHOLD", 3)
    monkeypatch.setattr(cb.settings, "CIRCUIT_BREAKER_COOLDOWN_SECONDS", 300)
    return r


def test_breaker_starts_closed(fake):
    assert cb.is_open("gemini") is False


def test_breaker_opens_after_threshold_consecutive_failures(fake):
    assert cb.record_failure("gemini") is False  # 1
    assert cb.record_failure("gemini") is False  # 2
    just_opened = cb.record_failure("gemini")    # 3 == threshold
    assert just_opened is True
    assert cb.is_open("gemini") is True


def test_breaker_open_is_per_provider(fake):
    for _ in range(3):
        cb.record_failure("gemini")
    assert cb.is_open("gemini") is True
    assert cb.is_open("chatgpt") is False


def test_record_failure_returns_true_only_once_on_open(fake):
    cb.record_failure("gemini")
    cb.record_failure("gemini")
    assert cb.record_failure("gemini") is True   # opened now
    assert cb.record_failure("gemini") is False  # already open, not "just opened"


def test_record_success_resets_failure_count(fake):
    cb.record_failure("gemini")
    cb.record_failure("gemini")
    cb.record_success("gemini")
    # count reset → two more failures should not open yet
    assert cb.record_failure("gemini") is False
    assert cb.record_failure("gemini") is False
    assert cb.is_open("gemini") is False


def test_no_redis_degrades_to_noop(monkeypatch):
    monkeypatch.setattr(cb, "_get_client", lambda: None)
    assert cb.is_open("gemini") is False
    assert cb.record_failure("gemini") is False
    cb.record_success("gemini")  # must not raise


@pytest.mark.parametrize("exc,expected", [
    (type("E", (Exception,), {"status_code": 429})(), True),
    (type("E", (Exception,), {"status_code": 402})(), True),
    (type("E", (Exception,), {"code": 429})(), True),
    (type("E", (Exception,), {"status": 429})(), True),
    (type("E", (Exception,), {"status_code": 500})(), False),
    (ValueError("nope"), False),
])
def test_is_rate_or_payment_error(exc, expected):
    assert cb.is_rate_or_payment_error(exc) is expected


def test_is_rate_or_payment_error_reads_response_status():
    resp = type("R", (), {"status_code": 429})()
    exc = type("E", (Exception,), {"response": resp})()
    assert cb.is_rate_or_payment_error(exc) is True
