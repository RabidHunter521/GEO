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


# ── Source capture: Claude web_search_result_location citations (Task 3) ─────
# anthropic 0.50 has no typed model for web-search citations; it materialises
# them loosely (type/url/title kept as attributes). Building through the SDK's
# own construct_type exercises exactly that path.

def _anthropic_message(content):
    from anthropic._models import construct_type
    from anthropic.types import Message

    return construct_type(type_=Message, value={
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-4-5",
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 4,
                  "server_tool_use": {"web_search_requests": 1}},
        "content": content,
    })


def _search_blocks(*urls):
    return [
        {"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {"query": "q"}},
        {"type": "web_search_tool_result", "tool_use_id": "srv_1", "content": [
            {"type": "web_search_result", "url": u, "title": u, "encrypted_content": "e",
             "page_age": None} for u in urls
        ]},
    ]


def _text(text, *cites):
    return {"type": "text", "text": text, "citations": [
        {"type": "web_search_result_location", "url": url, "title": title,
         "cited_text": "...", "encrypted_index": "i"} for url, title in cites
    ] or None}


def _claude_query(response):
    with patch("app.services.platform_clients.claude.anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        mock_anthropic.Anthropic.return_value = mock_client
        return ClaudeClient(api_key="fake-key").query("best dentist in KL")


def test_claude_captures_inline_citations_across_text_blocks_in_order():
    result = _claude_query(_anthropic_message([
        *_search_blocks("https://yelp.com/acme", "https://g2.com/acme", "https://unused.com"),
        _text("Acme Dental ", ("https://yelp.com/acme", "Acme on Yelp")),
        _text("is well rated.", ("https://g2.com/acme", "G2")),
    ]))

    assert [(c.url, c.title, c.rank) for c in result.citations] == [
        ("https://yelp.com/acme", "Acme on Yelp", 1),
        ("https://g2.com/acme", "G2", 2),
    ]
    assert result.text == "Acme Dental \nis well rated."


def test_claude_searched_but_uncited_pages_are_not_sources():
    result = _claude_query(_anthropic_message([
        *_search_blocks("https://yelp.com/acme"),
        _text("I could not find a clear answer."),
    ]))
    assert result.citations == ()


def test_claude_citations_collapse_duplicates_and_strip_fragments():
    result = _claude_query(_anthropic_message([
        _text("A", ("https://g2.com/acme#reviews", "G2"), ("https://g2.com/acme", "G2")),
        _text("B", ("https://g2.com/acme", "G2")),
    ]))
    assert [(c.url, c.rank) for c in result.citations] == [("https://g2.com/acme", 1)]


def test_claude_ignores_document_citations():
    doc_cite = {"type": "text", "text": "x", "citations": [
        {"type": "char_location", "cited_text": "x", "document_index": 0,
         "document_title": None, "start_char_index": 0, "end_char_index": 1},
    ]}
    assert _claude_query(_anthropic_message([doc_cite])).citations == ()


def test_claude_malformed_citations_yield_none_without_raising():
    text_block = MagicMock(type="text", text="ACME via Claude.", citations=42)
    mock_response = MagicMock(content=[text_block])
    mock_response.usage.input_tokens = 3
    mock_response.usage.output_tokens = 4
    result = _claude_query(mock_response)
    assert result.citations == ()
    assert result.text == "ACME via Claude."


# ── Source capture: Gemini grounding chunks (all-platform Task 4) ────────────
# Gemini links through opaque vertexaisearch redirects; the real domain
# arrives in web.domain / web.title and becomes SourceCitation.domain_hint.

_REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ"


def _gemini_grounded(chunks, text="Acme Dental is well rated."):
    candidate = {"content": {"role": "model", "parts": [{"text": text}]}}
    if chunks is not None:
        candidate["grounding_metadata"] = {"grounding_chunks": chunks}
    return types.GenerateContentResponse.model_validate({
        "candidates": [candidate],
        "usage_metadata": {"prompt_token_count": 10, "candidates_token_count": 20},
    })


def _gemini_query(response):
    with patch("app.services.platform_clients.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = response
        mock_genai.Client.return_value = mock_client
        return GeminiClient(api_key="fake-key").query("best dentist in KL")


def test_gemini_redirect_chunks_carry_the_real_domain_as_hint():
    result = _gemini_query(_gemini_grounded([
        {"web": {"uri": f"{_REDIRECT}1", "title": "www.yelp.com"}},
        {"web": {"uri": f"{_REDIRECT}2", "title": "g2.com", "domain": "g2.com"}},
    ]))

    assert [(c.url, c.rank, c.domain_hint, c.title) for c in result.citations] == [
        (f"{_REDIRECT}1", 1, "yelp.com", None),  # title is just the domain, not a page title
        (f"{_REDIRECT}2", 2, "g2.com", None),
    ]
    assert result.text == "Acme Dental is well rated."


def test_gemini_non_redirect_uri_keeps_title_and_needs_no_hint():
    result = _gemini_query(_gemini_grounded([
        {"web": {"uri": "https://acme.com/about?utm_source=gemini", "title": "About Acme"}},
    ]))
    assert [(c.url, c.title, c.domain_hint) for c in result.citations] == [
        ("https://acme.com/about", "About Acme", None),
    ]


def test_gemini_redirect_without_usable_domain_has_no_hint():
    result = _gemini_query(_gemini_grounded([{"web": {"uri": f"{_REDIRECT}1", "title": "Some page"}}]))
    assert len(result.citations) == 1
    assert result.citations[0].domain_hint is None


def test_gemini_skips_non_web_chunks():
    result = _gemini_query(_gemini_grounded([
        {"retrieved_context": {"uri": "gs://bucket/doc", "title": "doc"}},
        {"web": {"uri": "https://acme.com", "title": "Acme"}},
    ]))
    assert [c.url for c in result.citations] == ["https://acme.com"]


def test_gemini_ungrounded_answer_yields_no_citations():
    assert _gemini_query(_gemini_grounded(None)).citations == ()


def test_gemini_malformed_response_yields_no_citations_without_raising():
    # _gemini_response() is a MagicMock: candidates is not a real list.
    result = _gemini_query(_gemini_response())
    assert result.citations == ()
