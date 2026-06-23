# backend/tests/test_platform_clients.py
import pytest
from unittest.mock import patch, MagicMock

from google.genai import types

from app.services.platform_clients import get_platform_client, PlatformNotConfiguredError
from app.services.platform_clients.gemini import GeminiClient
from app.services.platform_clients.chatgpt import ChatGPTClient
from app.services.platform_clients.claude import ClaudeClient
from app.services.platform_clients.perplexity import PerplexityClient


# ── Gemini (retry policy is shared by all adapters via query_with_retry) ──────

def _gemini_response(text="ACME Corp is a leading consulting firm in KL.", prompt=10, candidates=20):
    mock_response = MagicMock()
    mock_response.text = text
    mock_response.usage_metadata.prompt_token_count = prompt
    mock_response.usage_metadata.candidates_token_count = candidates
    return mock_response


def test_gemini_query_returns_text_and_usage():
    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _gemini_response()
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result.text == "ACME Corp is a leading consulting firm in KL."
    assert result.model == "gemini-2.5-flash-lite"
    assert result.input_tokens == 10
    assert result.output_tokens == 20


def test_gemini_query_uses_google_search_grounding():
    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _gemini_response()
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        client.query("Tell me about ACME Corp")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.tools == [types.Tool(google_search=types.GoogleSearch())]


def test_gemini_query_retries_on_exception_then_succeeds():
    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            Exception("API error"),
            _gemini_response(text="ACME Corp response."),
        ]
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result.text == "ACME Corp response."
    assert mock_client.models.generate_content.call_count == 2


def test_gemini_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="GEMINI_API_KEY"):
        GeminiClient(api_key="")


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

def test_chatgpt_query_returns_output_text_and_usage():
    with patch("app.services.platform_clients.chatgpt.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = MagicMock(
            output_text="ACME via ChatGPT.",
            usage=MagicMock(input_tokens=5, output_tokens=8),
        )
        mock_openai.return_value = mock_client

        client = ChatGPTClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result.text == "ACME via ChatGPT."
    assert result.model == "gpt-5-mini"
    assert result.input_tokens == 5
    assert result.output_tokens == 8
    tools = mock_client.responses.create.call_args.kwargs["tools"]
    assert {"type": "web_search"} in tools


def test_chatgpt_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="OPENAI_API_KEY"):
        ChatGPTClient(api_key="")


# ── Perplexity ────────────────────────────────────────────────────────────────

def test_perplexity_query_parses_content_and_usage():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ACME via Perplexity."}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 9},
    }
    with patch("app.services.platform_clients.perplexity.httpx.post", return_value=mock_response):
        client = PerplexityClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result.text == "ACME via Perplexity."
    assert result.model == "sonar"
    assert result.input_tokens == 7
    assert result.output_tokens == 9


def test_perplexity_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="PERPLEXITY_API_KEY"):
        PerplexityClient(api_key="")


# ── Claude ────────────────────────────────────────────────────────────────────

def test_claude_query_joins_text_blocks_and_reports_usage():
    text_block = MagicMock(type="text", text="ACME via Claude.")
    tool_block = MagicMock(type="server_tool_use")
    mock_response = MagicMock(content=[tool_block, text_block])
    mock_response.usage.input_tokens = 3
    mock_response.usage.output_tokens = 4

    with patch("app.services.platform_clients.claude.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        client = ClaudeClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result.text == "ACME via Claude."
    assert result.model == "claude-haiku-4-5-20251001"
    assert result.input_tokens == 3
    assert result.output_tokens == 4


def test_claude_missing_key_raises_not_configured():
    with pytest.raises(PlatformNotConfiguredError, match="ANTHROPIC_API_KEY"):
        ClaudeClient(api_key="")


# ── Circuit breaker integration (query_with_retry) ────────────────────────────

def test_query_with_retry_skips_call_when_breaker_open():
    from app.services.platform_clients.base import query_with_retry
    from app.services.circuit_breaker import CircuitOpenError

    calls = []
    with patch("app.services.platform_clients.base.circuit_breaker") as mcb:
        mcb.is_open.return_value = True
        mcb.CircuitOpenError = CircuitOpenError
        with pytest.raises(CircuitOpenError):
            query_with_retry("gemini", lambda: calls.append(1))

    assert calls == []  # the provider was never called


def test_query_with_retry_records_success_on_ok_call():
    from app.services.platform_clients.base import query_with_retry, PlatformResult

    res = PlatformResult("t", "m", 1, 1)
    with patch("app.services.platform_clients.base.circuit_breaker") as mcb:
        mcb.is_open.return_value = False
        out = query_with_retry("gemini", lambda: res)

    assert out is res
    mcb.record_success.assert_called_once_with("gemini")


def test_query_with_retry_records_failure_on_rate_error():
    from app.services.platform_clients.base import query_with_retry, _MAX_ATTEMPTS

    def call():
        raise Exception("429 rate limited")

    with patch("app.services.platform_clients.base.circuit_breaker") as mcb:
        mcb.is_open.return_value = False
        mcb.is_rate_or_payment_error.return_value = True
        with pytest.raises(Exception, match="429"):
            query_with_retry("gemini", call)

    assert mcb.record_failure.call_count == _MAX_ATTEMPTS


def test_query_with_retry_ignores_non_rate_errors_for_breaker():
    from app.services.platform_clients.base import query_with_retry

    def call():
        raise ValueError("boom")

    with patch("app.services.platform_clients.base.circuit_breaker") as mcb:
        mcb.is_open.return_value = False
        mcb.is_rate_or_payment_error.return_value = False
        with pytest.raises(ValueError):
            query_with_retry("gemini", call)

    mcb.record_failure.assert_not_called()


# ── Factory ───────────────────────────────────────────────────────────────────

def test_get_platform_client_rejects_unknown_platform():
    with pytest.raises(ValueError, match="Unknown scan platform"):
        get_platform_client("bing")
