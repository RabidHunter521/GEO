# backend/app/services/circuit_breaker.py
"""Per-provider circuit breaker for scan platform calls.

When a scan platform returns repeated 429 (rate limit) / 402 (payment required)
responses, retrying immediately just adds load and burns money during an
incident. This breaker counts consecutive 429/402s per provider and, past a
threshold, "opens" — callers skip the provider for a cooldown.

State lives in Redis so it is shared across the API process and Celery workers.
Every Redis interaction is best-effort: if Redis is down or errors, the breaker
degrades to a no-op (always closed) and never blocks a scan.
"""
import time

import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Window over which consecutive failures are counted; a quiet provider lets the
# count expire so old blips don't accumulate into a false trip.
_FAIL_WINDOW_SECONDS = 120

# When Redis is unreachable, stop retrying it for this long so a down Redis can't
# add a connect-timeout to every scan query (it just degrades to a no-op).
_REDIS_DOWN_BACKOFF_SECONDS = 30

_client = None
_client_initialized = False
_redis_down_until = 0.0


def _mark_down() -> None:
    global _redis_down_until
    _redis_down_until = time.monotonic() + _REDIS_DOWN_BACKOFF_SECONDS


def _get_client():
    """Lazily build and cache a Redis client. Returns None if unavailable
    (or while in the down-backoff window after a recent failure)."""
    global _client, _client_initialized
    if time.monotonic() < _redis_down_until:
        return None
    if not _client_initialized:
        _client_initialized = True
        try:
            import redis

            _client = redis.Redis.from_url(
                settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2
            )
        except Exception:
            _client = None
    return _client


def _count_key(provider: str) -> str:
    return f"cb:fails:{provider}"


def _open_key(provider: str) -> str:
    return f"cb:open:{provider}"


def is_open(provider: str) -> bool:
    """True if the breaker is currently open for this provider."""
    c = _get_client()
    if c is None:
        return False
    try:
        return c.get(_open_key(provider)) is not None
    except Exception:
        _mark_down()
        return False


def record_failure(provider: str) -> bool:
    """Record a 429/402 failure. Returns True only on the call that trips the
    breaker open (so the caller can alert exactly once)."""
    c = _get_client()
    if c is None:
        return False
    try:
        key = _count_key(provider)
        count = c.incr(key)
        if count == 1:
            c.expire(key, _FAIL_WINDOW_SECONDS)
        if count >= settings.CIRCUIT_BREAKER_THRESHOLD:
            just_opened = c.set(
                _open_key(provider),
                "1",
                ex=settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS,
                nx=True,
            )
            c.delete(key)
            if just_opened:
                _alert_open(provider)
                logger.warning("circuit_breaker_opened", provider=provider)
            return bool(just_opened)
        return False
    except Exception:
        _mark_down()
        return False


def record_success(provider: str) -> None:
    """Reset the failure count after a successful call (consecutive semantics)."""
    c = _get_client()
    if c is None:
        return
    try:
        c.delete(_count_key(provider), _open_key(provider))
    except Exception:
        _mark_down()


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(exc, "response", None)
    if resp is not None:
        v = getattr(resp, "status_code", None)
        if isinstance(v, int):
            return v
    return None


def is_rate_or_payment_error(exc: Exception) -> bool:
    """True for provider 429 (rate limit) or 402 (payment required) errors."""
    return _status_code(exc) in (429, 402)


def _alert_open(provider: str) -> None:
    """Best-effort admin alert when a provider breaker trips. Never raises."""
    try:
        from app.core.constants import PLATFORM_LABELS
        from app.services import alert_service

        label = PLATFORM_LABELS.get(provider, provider)
        mins = settings.CIRCUIT_BREAKER_COOLDOWN_SECONDS // 60
        alert_service.dispatch_admin_alert(
            subject=f"Provider paused — repeated rate/quota errors: {label}",
            html_body=(
                f"<p>{label} returned repeated 429/402 responses and has been "
                f"paused for ~{mins} min to avoid hammering it and wasting spend. "
                f"Scans will skip {label} until it recovers.</p>"
            ),
            telegram_text=(
                f"⛔ <b>{label}</b> paused ~{mins} min — repeated rate/quota "
                f"errors (circuit breaker open)."
            ),
        )
    except Exception:
        logger.warning("circuit_breaker_alert_failed", provider=provider)


class CircuitOpenError(RuntimeError):
    """Raised when a provider's breaker is open, to skip the call fast."""

    def __init__(self, provider: str):
        super().__init__(f"Circuit breaker open for provider '{provider}'")
