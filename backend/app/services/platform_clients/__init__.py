# backend/app/services/platform_clients/__init__.py
from app.core.config import settings
from app.services.platform_clients.base import (
    PlatformClient,
    PlatformNotConfiguredError,
)
from app.services.platform_clients.chatgpt import ChatGPTClient
from app.services.platform_clients.claude import ClaudeClient
from app.services.platform_clients.gemini import GeminiClient
from app.services.platform_clients.perplexity import PerplexityClient

__all__ = [
    "PlatformClient",
    "PlatformNotConfiguredError",
    "get_platform_client",
]


def get_platform_client(platform: str) -> PlatformClient:
    if platform == "gemini":
        return GeminiClient(api_key=settings.GEMINI_API_KEY)
    if platform == "chatgpt":
        return ChatGPTClient(api_key=settings.OPENAI_API_KEY)
    if platform == "perplexity":
        return PerplexityClient(api_key=settings.PERPLEXITY_API_KEY)
    if platform == "claude":
        return ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    raise ValueError(f"Unknown scan platform: {platform}")
