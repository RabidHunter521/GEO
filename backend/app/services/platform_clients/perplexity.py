# backend/app/services/platform_clients/perplexity.py
import httpx

from app.services.platform_clients.base import (
    PlatformNotConfiguredError,
    query_with_retry,
)

API_URL = "https://api.perplexity.ai/chat/completions"
MODEL_NAME = "sonar"  # web-grounded by default
_TIMEOUT_SECONDS = 60.0


class PerplexityClient:
    platform = "perplexity"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "PERPLEXITY_API_KEY")
        self._api_key = api_key

    def query(self, prompt: str) -> str:
        def _call() -> str:
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
            return response.json()["choices"][0]["message"]["content"]

        return query_with_retry(self.platform, _call)
