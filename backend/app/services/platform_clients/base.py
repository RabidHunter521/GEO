# backend/app/services/platform_clients/base.py
"""Common interface for AI platform visibility-query clients."""
import re
import time
from dataclasses import dataclass
from typing import Iterable, Protocol, Callable

import structlog

from app.services import circuit_breaker
from app.services.provenance_service import canonical_source_url

logger = structlog.get_logger()

_MAX_ATTEMPTS = 2  # retry once on failure, per scan engine rules

# Wait before the retry. Retrying ~0.1s after a 429 reliably fails again (Gemini
# on Curlec), so honour the provider's own hint when it gives one, capped so a
# long hint cannot stall a scan; otherwise wait a short fixed delay.
_DEFAULT_RETRY_DELAY_SECONDS = 2.0
_MAX_RETRY_DELAY_SECONDS = 30.0
_sleep = time.sleep  # indirection so tests do not wait

# Google puts the hint in the error text ("Please retry in 37.5s",
# 'retryDelay': '37s') rather than a header.
_RETRY_HINT = re.compile(
    r"(?:retry in\s+|retryDelay['\"]?\s*:\s*['\"]?)(\d+(?:\.\d+)?)\s*s",
    re.IGNORECASE,
)

# The searcher's country, sent to every web search that accepts one. Without it
# a question with no place in it ("Is Curlec legit?") is answered for a US
# searcher. Names as stored on Client.country; unknown names send nothing.
_COUNTRY_CODES = {
    "malaysia": "MY", "singapore": "SG", "indonesia": "ID", "thailand": "TH",
    "philippines": "PH", "vietnam": "VN", "viet nam": "VN", "brunei": "BN",
    "brunei darussalam": "BN", "cambodia": "KH", "myanmar": "MM", "laos": "LA",
    "australia": "AU", "new zealand": "NZ", "india": "IN", "china": "CN",
    "hong kong": "HK", "taiwan": "TW", "japan": "JP", "south korea": "KR",
    "korea": "KR", "united arab emirates": "AE", "uae": "AE",
    "saudi arabia": "SA", "qatar": "QA", "united kingdom": "GB", "uk": "GB",
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "ireland": "IE", "germany": "DE", "france": "FR",
    "netherlands": "NL",
}
# SeenBy is Malaysia-first and the Google surfaces are already pinned to
# Malaysia, so a client with no country recorded is searched from Malaysia.
DEFAULT_COUNTRY_CODE = "MY"


def country_code(country: str | None) -> str | None:
    """ISO 3166-1 alpha-2 code for a client's country.

    Blank means the Malaysia default; a name not in the table returns None, and
    the search then runs without a location rather than from a guessed one.
    """
    if not isinstance(country, str) or not country.strip():
        return DEFAULT_COUNTRY_CODE
    value = " ".join(country.split())
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return _COUNTRY_CODES.get(value.casefold())


def retry_delay(exc: Exception) -> float:
    """Seconds to wait before retrying after `exc`."""
    seconds = None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        try:
            seconds = float(headers.get("retry-after"))
        except (TypeError, ValueError, AttributeError):
            seconds = None
    if seconds is None:
        match = _RETRY_HINT.search(str(exc))
        if match:
            seconds = float(match.group(1))
    if seconds is None or seconds < 0:
        return _DEFAULT_RETRY_DELAY_SECONDS
    return min(seconds, _MAX_RETRY_DELAY_SECONDS)


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
    # None = the surface always answers (every LLM platform). False = the
    # surface showed no AI answer for this question (Google AI Overviews):
    # a real observation, never a quote and never an error.
    answer_shown: bool | None = None


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
            if attempt + 1 < _MAX_ATTEMPTS:
                _sleep(retry_delay(exc))
    raise last_exc
