# backend/app/services/platform_clients/google_ai_mode.py
"""Google AI Mode: Google's conversational AI search tab. It always answers,
so a missing answer is an error (retried), unlike AI Overviews, and its rows
leave answer_shown unset like every LLM platform."""
from app.services.platform_clients import dataforseo
from app.services.platform_clients.base import (
    PlatformNotConfiguredError,
    PlatformResult,
    query_with_retry,
)

MODEL_NAME = "dataforseo-google-ai-mode"


class GoogleAIModeClient:
    platform = "google_ai_mode"
    supports_repeat_samples = False  # see GoogleAIOverviewClient

    def __init__(self, login: str, password: str):
        if not login or not password:
            raise PlatformNotConfiguredError(self.platform, "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD")
        self._login = login
        self._password = password

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            result = dataforseo.post_task(
                self._login, self._password, dataforseo.AI_MODE_ENDPOINT, prompt,
            )
            return dataforseo.to_result(
                dataforseo.find_ai_answer(result), MODEL_NAME, answer_always_shown=True,
            )

        return query_with_retry(self.platform, _call)
