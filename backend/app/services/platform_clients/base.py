# backend/app/services/platform_clients/base.py
"""Common interface for AI platform visibility-query clients."""
from dataclasses import dataclass
from typing import Iterable, Protocol, Callable

import structlog

from app.services import circuit_breaker
from app.services.provenance_service import canonical_source_url

logger = structlog.get_logger()

_MAX_ATTEMPTS = 2  # retry once on failure, per scan engine rules


@dataclass(frozen=True)
class SourceCitation:
    """A single source the platform reported using to answer a query."""

    url: str
    title: str | None
    rank: int  # 1-based position in the platform's source list
    # Real domain when `url` is a grounding redirect (GROUNDING_REDIRECT_HOSTS)
    # whose host says nothing about the source; None for ordinary URLs.
    domain_hint: str | None = None


@dataclass(frozen=True)
class PlatformResult:
    """A platform query's answer plus the token usage it billed.

    Usage travels with the answer so the scan engine can cost-log every query
    (the providers expose usage in different shapes; each adapter normalizes it).

    search_requests is the billable web-search / grounded-request count for the
    call. Every platform runs search-enabled, and providers charge per request
    on top of tokens, so cost is wrong without it.
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    citations: tuple[SourceCitation, ...] = ()
    search_requests: int = 0


def collect_citations(
    entries: Iterable[tuple[object, object, str | None]],
) -> tuple[SourceCitation, ...]:
    """(url, title, domain_hint) entries in answer order -> SourceCitations.

    Shared by the adapters that parse sources out of SDK objects: URLs are
    canonicalised (utm_* + fragment stripped) so one page is one source,
    repeats collapse to their first rank, and anything that isn't a
    non-empty string is dropped rather than trusted.
    """
    seen: set[str] = set()
    out: list[SourceCitation] = []
    for url, title, hint in entries:
        if not isinstance(url, str) or not url:
            continue
        canonical = canonical_source_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(SourceCitation(
            url=canonical,
            title=title if isinstance(title, str) and title else None,
            rank=len(out) + 1,
            domain_hint=hint,
        ))
    return tuple(out)


def field_of(obj, name: str):
    """Attribute or dict key — SDKs materialise unknown variants either way."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


# Per-call HTTP timeout for every platform query. Bounds a single hung provider
# call so it can't pin a Celery worker (which also has a hard time limit). SDK
# clients set this AND disable their own retries — query_with_retry owns retries.
PLATFORM_QUERY_TIMEOUT_SECONDS = 90.0


class PlatformClient(Protocol):
    platform: str

    def query(self, prompt: str) -> PlatformResult:
        """Send a visibility query and return the answer text plus token usage."""
        ...


class PlatformNotConfiguredError(RuntimeError):
    """Raised when a platform's API key is missing from settings."""

    def __init__(self, platform: str, env_var: str):
        super().__init__(f"Platform '{platform}' is not configured: set {env_var}")


def query_with_retry(platform: str, call: Callable[[], PlatformResult]) -> PlatformResult:
    """Run a platform call with retry-once, gated by the provider circuit breaker.

    If the breaker is open (provider has been 429/402-ing), skip the call fast so
    we don't hammer it or waste spend. A successful call resets the breaker; each
    429/402 failure is counted toward tripping it."""
    if circuit_breaker.is_open(platform):
        logger.warning("platform_query_skipped_circuit_open", platform=platform)
        raise circuit_breaker.CircuitOpenError(platform)

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            result = call()
            circuit_breaker.record_success(platform)
            return result
        except Exception as exc:
            last_exc = exc
            if circuit_breaker.is_rate_or_payment_error(exc):
                circuit_breaker.record_failure(platform)
            logger.warning(
                "platform_query_failed",
                platform=platform,
                attempt=attempt + 1,
                error=str(exc),
            )
    raise last_exc
