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


def _client_ip(request: Request) -> str:
    if settings.RATE_LIMIT_TRUSTED_PROXY:
        # Behind a reverse proxy: take the rightmost XFF entry, which is
        # appended by the proxy from its own $remote_addr and cannot be forged
        # by the client. The leftmost entries are client-controlled.
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()
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
