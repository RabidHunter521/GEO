# backend/app/services/platform_clients/claude.py
import anthropic
import structlog

from app.services.claude_client import web_search_requests
from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    PlatformResult,
    SourceCitation,
    collect_citations,
    field_of,
    query_with_retry,
)

logger = structlog.get_logger()

# Same model family as the toolkit generators (see claude_client.py); web search
# keeps answers close to what real Claude users see.
MODEL_NAME = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024


def _parse_citations(response) -> tuple[SourceCitation, ...]:
    """Sources the answer cites inline: web_search_result_location citations
    on its text blocks, in answer order.

    Pages the search returned but the answer never cites (the
    web_search_tool_result block) are not counted, matching ChatGPT's
    "cited inline" semantics. anthropic 0.50 has no typed model for these
    citations and keeps them as loose objects, so fields are read by name.
    Defensive: a parsing slip returns () and never fails the query.
    """
    try:
        return collect_citations(
            (field_of(cite, "url"), field_of(cite, "title"), None)
            for block in response.content
            if field_of(block, "type") == "text"
            for cite in field_of(block, "citations") or []
            if field_of(cite, "type") == "web_search_result_location"
        )
    except Exception as exc:
        logger.warning("citation_parse_failed", platform="claude", error=str(exc))
        return ()


class ClaudeClient:
    platform = "claude"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "ANTHROPIC_API_KEY")
        # max_retries=0: query_with_retry owns the retry-once policy.
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=PLATFORM_QUERY_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            response = self._client.messages.create(
                model=MODEL_NAME,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
            text = "\n".join(
                block.text for block in response.content if block.type == "text"
            )
            return PlatformResult(
                text=text,
                model=MODEL_NAME,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                citations=_parse_citations(response),
                search_requests=web_search_requests(response),
            )

        return query_with_retry(self.platform, _call)
