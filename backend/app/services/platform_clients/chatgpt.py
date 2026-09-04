# backend/app/services/platform_clients/chatgpt.py
from openai import OpenAI

from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    PlatformResult,
    query_with_retry,
)

# Web search keeps answers close to what real ChatGPT users see.
MODEL_NAME = "gpt-5-mini"


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


class ChatGPTClient:
    platform = "chatgpt"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "OPENAI_API_KEY")
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
                tools=[{"type": "web_search"}],
            )
            return PlatformResult(
                text=response.output_text,
                model=MODEL_NAME,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                search_requests=_search_calls(response),
            )

        return query_with_retry(self.platform, _call)
