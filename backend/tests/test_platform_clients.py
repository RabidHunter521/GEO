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


# ── Source capture: ChatGPT url_citation annotations (all-platform Task 2) ───
# Built with the real SDK constructor (not MagicMock) so a response-shape
# change in the openai package fails here instead of silently capturing nothing.

def _openai_response(annotations, *, extra_output=()):
    from openai._models import construct_type
    from openai.types.responses import Response

    return construct_type(type_=Response, value={
        "id": "resp_1", "object": "response", "created_at": 0, "model": "gpt-5-mini",
        "status": "completed", "parallel_tool_calls": True, "tool_choice": "auto",
        "tools": [],
        "output": [
            {"type": "web_search_call", "id": "ws_1", "status": "completed"},
            *extra_output,
            {
                "type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "Acme Dental is well rated.",
                             "annotations": annotations}],
            },
        ],
        "usage": {"input_tokens": 5, "output_tokens": 8, "total_tokens": 13,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    })


def _url_citation(url, title="T", start=0, end=4):
    return {"type": "url_citation", "url": url, "title": title,
            "start_index": start, "end_index": end}


def _chatgpt_query(response):
    with patch("app.services.platform_clients.chatgpt.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = response
        mock_openai.return_value = mock_client
        return ChatGPTClient(api_key="fake-key").query("best dentist in KL")


def test_chatgpt_captures_url_citations_in_answer_order():
    result = _chatgpt_query(_openai_response([
        _url_citation("https://www.yelp.com/biz/acme", "Acme on Yelp"),
        _url_citation("https://g2.com/acme", "G2"),
    ]))

    assert [(c.url, c.title, c.rank) for c in result.citations] == [
        ("https://www.yelp.com/biz/acme", "Acme on Yelp", 1),
        ("https://g2.com/acme", "G2", 2),
    ]
    assert all(c.domain_hint is None for c in result.citations)


def test_chatgpt_citations_strip_utm_and_collapse_duplicates():
    result = _chatgpt_query(_openai_response([
        _url_citation("https://g2.com/acme?utm_source=openai", "G2"),
        _url_citation("https://yelp.com/acme?utm_source=openai", "Yelp"),
        _url_citation("https://g2.com/acme", "G2 again"),
    ]))

    assert [(c.url, c.rank) for c in result.citations] == [
        ("https://g2.com/acme", 1),
        ("https://yelp.com/acme", 2),
    ]


def test_chatgpt_no_annotations_yields_no_citations():
    assert _chatgpt_query(_openai_response([])).citations == ()


def test_chatgpt_ignores_non_url_annotations():
    file_cite = {"type": "file_citation", "file_id": "f1", "filename": "x.pdf", "index": 0}
    result = _chatgpt_query(_openai_response([file_cite, _url_citation("https://g2.com/a")]))
    assert [c.url for c in result.citations] == ["https://g2.com/a"]


def test_chatgpt_malformed_response_yields_no_citations_without_raising():
    # MagicMock .output is not iterable — the parser must swallow that.
    result = _chatgpt_query(MagicMock(output_text="x", usage=MagicMock(input_tokens=1, output_tokens=1)))
    assert result.citations == ()
    assert result.text == "x"
