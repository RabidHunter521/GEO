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


_LEFTMOST = "leftmost"


def _trusted_proxy_mode() -> int | str:
    """How to read X-Forwarded-For, from RATE_LIMIT_TRUSTED_PROXY.

    Returns 0 (no proxy — ignore the header), the string "leftmost", or a
    positive hop count. The two non-zero modes exist because the two proxy
    families behave oppositely, and picking the wrong one silently breaks the
    limiter rather than erroring:

    * **Append-only proxies** (Caddy, Nginx) forward whatever XFF the client
      sent and append to it, so leading entries are attacker-controlled and the
      client is the Nth entry from the RIGHT. -> set a hop count.
    * **Stripping edges** (Railway, Cloudflare) discard the client's XFF and
      rebuild the chain, so the LEFTMOST entry is authoritative. These platforms
      also do not guarantee a stable internal hop count, which makes counting
      from the right actively unsafe there. -> set "leftmost".

    The setting began life as a bare on/off flag, so any other truthy value
    still means exactly one hop.
    """
    raw = str(settings.RATE_LIMIT_TRUSTED_PROXY).strip().lower()
    if not raw:
        return 0
    if raw == _LEFTMOST:
        return _LEFTMOST
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def _client_ip(request: Request) -> str:
    mode = _trusted_proxy_mode()
    if mode:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                if mode == _LEFTMOST:
                    return parts[0]
                if len(parts) >= mode:
                    return parts[-mode]
                # Shorter chain than configured: the request did not come
                # through the proxy path we were told about, so trust none of
                # the header and fall through to the peer address.
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
