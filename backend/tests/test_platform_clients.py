# backend/tests/test_platform_clients.py
import pytest
from unittest.mock import patch, MagicMock

from app.services.platform_clients import get_platform_client, PlatformNotConfiguredError
from app.services.platform_clients.gemini import GeminiClient
from app.services.platform_clients.chatgpt import ChatGPTClient
from app.services.platform_clients.claude import ClaudeClient
from app.services.platform_clients.perplexity import PerplexityClient


# ── Gemini (retry policy is shared by all adapters via query_with_retry) ──────

def test_gemini_query_returns_text_response():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp is a leading consulting firm in KL."

    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp is a leading consulting firm in KL."


def test_gemini_query_retries_on_exception_then_succeeds():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp response."

    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [Exception("API error"), mock_response]
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp response."
    assert mock_client.models.generate_content.call_count == 2


def test_gemini_query_raises_after_two_failures():
    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API error")
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        with pytest.raises(Exception, match="API error"):
            client.query("Tell me about ACME Corp")

    assert mock_client.models.generate_content.call_count == 2


# ── ChatGPT ───────────────────────────────────────────────────────────────────

def test_chatgpt_query_returns_output_text():
    with patch("app.services.platform_clients.chatgpt.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = MagicMock(output_text="ACME via ChatGPT.")
        mock_openai.return_value = mock_client

        client = ChatGPTClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME via ChatGPT."
    tools = mock_client.responses.create.call_args.kwargs["tools"]
    assert {"type": "web_search"} in tools


def test_chatgpt_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="OPENAI_API_KEY"):
        ChatGPTClient(api_key="")


# ── Perplexity ────────────────────────────────────────────────────────────────

def test_perplexity_query_parses_choice_content():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ACME via Perplexity."}}]
    }
    with patch("app.services.platform_clients.perplexity.httpx.post", return_value=mock_response):
        client = PerplexityClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME via Perplexity."


def test_perplexity_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="PERPLEXITY_API_KEY"):
        PerplexityClient(api_key="")


# ── Claude ────────────────────────────────────────────────────────────────────

def test_claude_query_joins_text_blocks():
    text_block = MagicMock(type="text", text="ACME via Claude.")
    tool_block = MagicMock(type="server_tool_use")
    mock_response = MagicMock(content=[tool_block, text_block])

    with patch("app.services.platform_clients.claude.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        client = ClaudeClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME via Claude."


def test_claude_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="ANTHROPIC_API_KEY"):
        ClaudeClient(api_key="")


# ── Factory ───────────────────────────────────────────────────────────────────

def test_get_platform_client_rejects_unknown_platform():
    with pytest.raises(ValueError, match="Unknown scan platform"):
        get_platform_client("bing")
