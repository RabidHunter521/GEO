# backend/app/services/platform_clients/gemini.py
from urllib.parse import urlparse

import structlog
from google import genai
from google.genai import types

from app.core.constants import GROUNDING_REDIRECT_HOSTS
from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    PlatformResult,
    SourceCitation,
    collect_citations,
    field_of,
    query_with_retry,
)
from app.services.provenance_service import normalize_domain

logger = structlog.get_logger()

MODEL_NAME = "gemini-2.5-flash-lite"


def _web_entry(web) -> tuple[object, object, str | None]:
    """(url, title, domain_hint) for one grounding chunk's `web` source.

    Gemini links through an opaque vertexaisearch redirect and puts the real
    domain in `domain` (newer SDKs) or `title` — for those, the domain becomes
    the hint and the title is dropped (it is not a page title). Ordinary URLs
    keep their title and need no hint.
    """
    uri = field_of(web, "uri")
    title = field_of(web, "title")
    host = urlparse(uri).hostname if isinstance(uri, str) else None
    if host not in GROUNDING_REDIRECT_HOSTS:
        return uri, title, None
    raw_domain = field_of(web, "domain") or title
    hint = normalize_domain(raw_domain) if isinstance(raw_domain, str) else ""
    return uri, None, hint or None


def _parse_citations(response) -> tuple[SourceCitation, ...]:
    """Sources Gemini grounded its answer in: the web grounding chunks of the
    first candidate, in order. Non-web chunks (maps, retrieved context) are
    skipped. Defensive: a parsing slip returns () and never fails the query.
    """
    try:
        metadata = field_of(response.candidates[0], "grounding_metadata")
        chunks = field_of(metadata, "grounding_chunks") if metadata is not None else None
        return collect_citations(
            _web_entry(web)
            for chunk in chunks or []
            if (web := field_of(chunk, "web")) is not None
        )
    except Exception as exc:
        logger.warning("citation_parse_failed", platform="gemini", error=str(exc))
        return ()


class GeminiClient:
    platform = "gemini"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "GEMINI_API_KEY")
        # http_options timeout is in milliseconds (per google-genai SDK).
        self._client = genai.Client(
            api_key=api_key,
            http_options={"timeout": int(PLATFORM_QUERY_TIMEOUT_SECONDS * 1000)},
        )

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            # Grounding with Google Search keeps answers close to what a real
            # Gemini user sees, matching the web-search setup on the other platforms.
            response = self._client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            usage = response.usage_metadata
            return PlatformResult(
                text=response.text,
                model=MODEL_NAME,
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                citations=_parse_citations(response),
                # Google bills grounding per grounded prompt, not per search.
                search_requests=1,
            )

        return query_with_retry(self.platform, _call)
