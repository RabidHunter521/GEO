# backend/app/services/platform_clients/base.py
"""Common interface for AI platform visibility-query clients."""
from typing import Protocol, Callable

import structlog

logger = structlog.get_logger()

_MAX_ATTEMPTS = 2  # retry once on failure, per scan engine rules


class PlatformClient(Protocol):
    platform: str

    def query(self, prompt: str) -> str:
        """Send a visibility query and return the platform's answer text."""
        ...


class PlatformNotConfiguredError(RuntimeError):
    """Raised when a platform's API key is missing from settings."""

    def __init__(self, platform: str, env_var: str):
        super().__init__(f"Platform '{platform}' is not configured: set {env_var}")


def query_with_retry(platform: str, call: Callable[[], str]) -> str:
    """Run a platform call with the standard retry-once policy."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return call()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "platform_query_failed",
                platform=platform,
                attempt=attempt + 1,
                error=str(exc),
            )
    raise last_exc
