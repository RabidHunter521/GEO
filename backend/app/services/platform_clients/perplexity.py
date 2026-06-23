# backend/app/services/platform_clients/perplexity.py
import httpx

from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    PlatformResult,
    query_with_retry,
)

API_URL = "https://api.perplexity.ai/chat/completions"
MODEL_NAME = "sonar"  # web-grounded by default
_TIMEOUT_SECONDS = PLATFORM_QUERY_TIMEOUT_SECONDS


class PerplexityClient:
    platform = "perplexity"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "PERPLEXITY_API_KEY")
        self._api_key = api_key

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            response = httpx.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            usage = payload.get("usage") or {}
            return PlatformResult(
                text=payload["choices"][0]["message"]["content"],
                model=MODEL_NAME,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )

        return query_with_retry(self.platform, _call)
