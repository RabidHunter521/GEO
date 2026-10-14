# backend/app/services/platform_clients/__init__.py
from app.core.config import settings
from app.services.platform_clients.base import (
    PlatformClient,
    PlatformNotConfiguredError,
)
from app.services.platform_clients.chatgpt import ChatGPTClient
from app.services.platform_clients.claude import ClaudeClient
from app.services.platform_clients.gemini import GeminiClient
from app.services.platform_clients.google_ai_mode import GoogleAIModeClient
from app.services.platform_clients.google_ai_overview import GoogleAIOverviewClient
from app.services.platform_clients.perplexity import PerplexityClient

__all__ = [
    "PlatformClient",
    "PlatformNotConfiguredError",
    "get_platform_client",
]


def get_platform_client(platform: str, country_code: str | None = None) -> PlatformClient:
    """A query client for `platform`.

    `country_code` (ISO alpha-2) is the searcher's country for web search.
    ChatGPT, Claude and Perplexity take it; Gemini's Google Search grounding
    has no location setting, and the Google surfaces are pinned to Malaysia.
    """
    if platform == "gemini":
        return GeminiClient(api_key=settings.GEMINI_API_KEY)
    if platform == "chatgpt":
        return ChatGPTClient(api_key=settings.OPENAI_API_KEY, country_code=country_code)
    if platform == "perplexity":
        return PerplexityClient(api_key=settings.PERPLEXITY_API_KEY, country_code=country_code)
    if platform == "claude":
        return ClaudeClient(api_key=settings.ANTHROPIC_API_KEY, country_code=country_code)
    if platform == "google_aio":
        return GoogleAIOverviewClient(settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD)
    if platform == "google_ai_mode":
        return GoogleAIModeClient(settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD)
    raise ValueError(f"Unknown scan platform: {platform}")
