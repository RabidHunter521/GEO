"""Lightweight per-IP fixed-window rate limiting, backed by Redis.

Used to protect the unauthenticated public client view. The limiter **fails
open**: if Redis is unreachable the request is allowed through — a limiter
outage must never take down the client-facing surface.
"""
import redis
import structlog
from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = structlog.get_logger()

_redis_client = None


def _get_redis() -> "redis.Redis":
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
    return _redis_client


def _trusted_proxy_hops() -> int:
    """How many proxies sit in front of the app. 0 = none (ignore XFF entirely).

    The setting began life as a bare on/off flag, so any truthy non-numeric
    value still means exactly one hop.
    """
    raw = str(settings.RATE_LIMIT_TRUSTED_PROXY).strip()
    if not raw:
        return 0
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _client_ip(request: Request) -> str:
    hops = _trusted_proxy_hops()
    if hops:
        # Each proxy appends the address it received the connection from, so
        # with N trusted proxies the client is the Nth entry from the right.
        # Everything further left is client-supplied and forgeable; the entries
        # to the right are our own infrastructure. Keying on the rightmost when
        # two proxies are in front (Railway, Vercel) would bucket every visitor
        # under one platform IP and turn the limiter into a global cap.
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if len(parts) >= hops:
                return parts[-hops]
            # Shorter chain than configured: the request did not come through
            # the proxy path we were told about, so trust none of the header.
    return request.client.host if request.client else "unknown"


def rate_limit(namespace: str, max_requests: int, window_seconds: int):
    """Build a FastAPI dependency enforcing `max_requests` per `window_seconds`
    per client IP, scoped to `namespace` (so all routes sharing it share a
    budget). Raises 429 when exceeded; allows through on any Redis error.
    """

    def dependency(request: Request) -> None:
        key = f"rl:{namespace}:{_client_ip(request)}"
        try:
            client = _get_redis()
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
            if count > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down.",
                )
        except HTTPException:
            raise
        except Exception as exc:  # fail open — never block the view on infra
            logger.warning("rate_limit_unavailable", namespace=namespace, error=str(exc))

    return dependency
