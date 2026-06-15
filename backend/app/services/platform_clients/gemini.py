# backend/app/services/platform_clients/gemini.py
from google import genai
from google.genai import types

from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    query_with_retry,
)

MODEL_NAME = "gemini-2.5-flash-lite"


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

    def query(self, prompt: str) -> str:
        def _call() -> str:
            # Grounding with Google Search keeps answers close to what a real
            # Gemini user sees, matching the web-search setup on the other platforms.
            response = self._client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            return response.text

        return query_with_retry(self.platform, _call)
