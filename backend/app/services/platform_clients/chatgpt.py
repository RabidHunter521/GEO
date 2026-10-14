# backend/app/services/platform_clients/chatgpt.py
import structlog
from openai import OpenAI

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

# Web search keeps answers close to what real ChatGPT users see.
MODEL_NAME = "gpt-5-mini"
MODEL_DISPLAY_NAME = "GPT-5 mini"  # named in the client-facing methodology


def _search_calls(response) -> int:
    """Billable web_search tool calls in a Responses API result.

    OpenAI charges per call, and the model does not always search, so this
    counts rather than assuming one. Defensive: a cost-logging slip must never
    break a scan, and tests pass mocks whose .output is not iterable.
    """
    try:
        return sum(
            1 for item in response.output
            if getattr(item, "type", "") == "web_search_call"
        )
    except Exception:
        return 0


def _parse_citations(response) -> tuple[SourceCitation, ...]:
    """Sources the answer cites inline: url_citation annotations on the
    message's output_text parts, in answer order.

    Searched-but-uncited pages are not counted, so "a source" means the same
    thing here as on Claude. Defensive: a parsing slip returns () and never
    fails the query.
    """
    try:
        return collect_citations(
            (field_of(ann, "url"), field_of(ann, "title"), None)
            for item in response.output
            if field_of(item, "type") == "message"
            for part in field_of(item, "content") or []
            for ann in field_of(part, "annotations") or []
            if field_of(ann, "type") == "url_citation"
        )
    except Exception as exc:
        logger.warning("citation_parse_failed", platform="chatgpt", error=str(exc))
        return ()


class ChatGPTClient:
    platform = "chatgpt"

    def __init__(self, api_key: str, country_code: str | None = None):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "OPENAI_API_KEY")
        self._web_search: dict = {"type": "web_search"}
        if country_code:
            self._web_search["user_location"] = {"type": "approximate", "country": country_code}
        # max_retries=0: query_with_retry owns the retry-once policy.
        self._client = OpenAI(
            api_key=api_key,
            timeout=PLATFORM_QUERY_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            response = self._client.responses.create(
                model=MODEL_NAME,
                input=prompt,
                tools=[self._web_search],
            )
            if getattr(response, "status", None) == "incomplete":
                # A cut-off answer can drop the brand from the end of a list.
                logger.warning(
                    "platform_answer_truncated", platform=self.platform,
                    reason=str(getattr(response, "incomplete_details", None)),
                )
            return PlatformResult(
                text=response.output_text,
                model=MODEL_NAME,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                citations=_parse_citations(response),
                search_requests=_search_calls(response),
            )

        return query_with_retry(self.platform, _call)
