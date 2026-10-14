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
MODEL_DISPLAY_NAME = "Claude Haiku 4.5"  # named in the client-facing methodology
# 1024 cut long ranked lists short, and a brand near the end of a cut list is
# recorded as Not seen by AI.
_MAX_TOKENS = 2048
# A turn that runs long server-side web searches can come back with
# stop_reason "pause_turn" and an unfinished answer; it is resumed by sending
# the partial assistant content back. Bounded so one question stays cheap.
_MAX_CONTINUATIONS = 2


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


def _merge_citations(responses) -> tuple[SourceCitation, ...]:
    """Inline citations across a paused-and-resumed answer, re-ranked as one."""
    if len(responses) == 1:
        return _parse_citations(responses[0])
    return collect_citations(
        (c.url, c.title, c.domain_hint) for r in responses for c in _parse_citations(r)
    )


class ClaudeClient:
    platform = "claude"

    def __init__(self, api_key: str, country_code: str | None = None):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "ANTHROPIC_API_KEY")
        self._web_search: dict = {"type": "web_search_20250305", "name": "web_search"}
        if country_code:
            self._web_search["user_location"] = {"type": "approximate", "country": country_code}
        # max_retries=0: query_with_retry owns the retry-once policy.
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=PLATFORM_QUERY_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            messages: list[dict] = [{"role": "user", "content": prompt}]
            responses = []
            for _ in range(1 + _MAX_CONTINUATIONS):
                response = self._client.messages.create(
                    model=MODEL_NAME,
                    max_tokens=_MAX_TOKENS,
                    messages=messages,
                    tools=[self._web_search],
                )
                responses.append(response)
                if getattr(response, "stop_reason", None) != "pause_turn":
                    break
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": [
                        block for r in responses for block in r.content
                    ]},
                ]
            if getattr(responses[-1], "stop_reason", None) in ("max_tokens", "pause_turn"):
                logger.warning(
                    "platform_answer_truncated", platform=self.platform,
                    reason=responses[-1].stop_reason,
                )
            text = "\n".join(
                block.text
                for r in responses for block in r.content if block.type == "text"
            )
            return PlatformResult(
                text=text,
                model=MODEL_NAME,
                input_tokens=sum(r.usage.input_tokens for r in responses),
                output_tokens=sum(r.usage.output_tokens for r in responses),
                citations=_merge_citations(responses),
                search_requests=sum(web_search_requests(r) for r in responses),
            )

        return query_with_retry(self.platform, _call)
