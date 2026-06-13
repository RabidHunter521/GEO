# backend/app/services/platform_clients/gemini.py
from google import genai

from app.services.platform_clients.base import (
    PlatformNotConfiguredError,
    query_with_retry,
)

MODEL_NAME = "gemini-2.5-flash-lite"


class GeminiClient:
    platform = "gemini"

    def __init__(self, api_key: str):
        if not api_key:
            raise PlatformNotConfiguredError(self.platform, "GEMINI_API_KEY")
        self._client = genai.Client(api_key=api_key)

    def query(self, prompt: str) -> str:
        def _call() -> str:
            response = self._client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return response.text

        return query_with_retry(self.platform, _call)
