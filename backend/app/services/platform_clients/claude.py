# backend/app/services/platform_clients/claude.py
import anthropic

from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    query_with_retry,
)

# Same model family as the toolkit generators (see claude_client.py); web search
# keeps answers close to what real Claude users see.
MODEL_NAME = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024


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

    def query(self, prompt: str) -> str:
        def _call() -> str:
            response = self._client.messages.create(
                model=MODEL_NAME,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            )
            return "\n".join(
                block.text for block in response.content if block.type == "text"
            )

        return query_with_retry(self.platform, _call)
