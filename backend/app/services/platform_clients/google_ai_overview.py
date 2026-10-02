# backend/app/services/platform_clients/google_ai_overview.py
"""Google AI Overviews: the AI answer at the top of an ordinary Google search.

Not every search shows one. A search without an overview is a real
observation (`answer_shown=False`), never an error and never a quote.
"""
from app.services.platform_clients import dataforseo
from app.services.platform_clients.base import (
    PlatformNotConfiguredError,
    PlatformResult,
    query_with_retry,
)

MODEL_NAME = "dataforseo-google-aio"


class GoogleAIOverviewClient:
    platform = "google_aio"
    # Re-running the same Google search seconds apart buys the same page and
    # trips the vendor's duplicate-task limits; repeat samples are skipped.
    supports_repeat_samples = False

    def __init__(self, login: str, password: str):
        if not login or not password:
            raise PlatformNotConfiguredError(self.platform, "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD")
        self._login = login
        self._password = password

    def query(self, prompt: str) -> PlatformResult:
        def _call() -> PlatformResult:
            result = dataforseo.post_task(
                self._login, self._password, dataforseo.AI_OVERVIEW_ENDPOINT, prompt,
                # Many overviews render after the page loads; without this they
                # come back missing and a shown overview reads as "none".
                load_async_ai_overview=True,
            )
            return dataforseo.to_result(
                dataforseo.find_ai_answer(result), MODEL_NAME, answer_always_shown=False,
            )

        return query_with_retry(self.platform, _call)
