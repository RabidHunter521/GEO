from unittest.mock import MagicMock, patch

from app.services.platform_clients import perplexity
from app.services.platform_clients.base import SourceCitation


def _payload(extra: dict) -> dict:
    base = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    base.update(extra)
    return base


def _patch_post(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return patch.object(perplexity.httpx, "post", return_value=resp)


def test_parses_search_results_shape():
    payload = _payload({"search_results": [
        {"title": "Best CRMs", "url": "https://a.com/x", "date": "2026-01-01"},
        {"title": None, "url": "https://b.com/y"},
    ]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert result.citations == (
        SourceCitation(url="https://a.com/x", title="Best CRMs", rank=1),
        SourceCitation(url="https://b.com/y", title=None, rank=2),
    )


def test_falls_back_to_legacy_citations_list():
    payload = _payload({"citations": ["https://a.com/x", "https://b.com/y"]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert [c.url for c in result.citations] == ["https://a.com/x", "https://b.com/y"]
    assert result.citations[0].rank == 1


def test_no_sources_yields_empty_tuple():
    with _patch_post(_payload({})):
        result = perplexity.PerplexityClient("key").query("q")
    assert result.citations == ()


def test_skips_entries_without_url():
    payload = _payload({"search_results": [{"title": "x"}, {"url": "https://b.com/y"}]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert [c.url for c in result.citations] == ["https://b.com/y"]
    assert result.citations[0].rank == 1
