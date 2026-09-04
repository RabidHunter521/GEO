from unittest.mock import MagicMock, patch

from app.services import content_analysis_service as svc
from app.services.content_crawler import CrawlResult


def _client():
    c = MagicMock()
    c.id = "00000000-0000-0000-0000-000000000001"
    c.name = "Solar Malaysia"
    c.industry = "solar installation"
    c.website = "https://solar.example"
    return c


def _text(s):
    resp = MagicMock()
    block = MagicMock()
    block.text = s
    resp.content = [block]
    return resp


def test_coverage_score_math():
    entities = [
        {"entity": "a", "covered": True},
        {"entity": "b", "covered": True},
        {"entity": "c", "covered": False},
        {"entity": "d", "covered": False},
    ]
    assert svc._coverage_score(entities) == 50.0


def test_coverage_score_empty():
    assert svc._coverage_score([]) == 0.0


def test_analyze_content_assembles_payload():
    crawl = CrawlResult(
        pages_crawled=5,
        text_corpus="solar panels and inverters",
        word_count=120,
        h1_count=4,
        faq_count=1,
        blog_count=2,
        schema_present=True,
    )

    te_json = (
        '{"topics": [{"topic": "Solar Panels", "status": "strong"},'
        ' {"topic": "Net Metering", "status": "missing"}],'
        ' "entities": [{"entity": "Inverter", "covered": true},'
        ' {"entity": "Battery Storage", "covered": false}]}'
    )

    # Calls run concurrently in threads, so dispatch on prompt content (not order).
    # **kwargs so adding a call parameter (temperature, system, …) cannot make
    # this mock raise TypeError inside a worker thread, where the failure was
    # swallowed and surfaced only as an unexplained 0.0 coverage score.
    def create(model, max_tokens, messages, **kwargs):
        prompt = messages[0]["content"]
        if "Output ONLY valid JSON" in prompt:
            return _text(te_json)
        return _text("Add a dedicated battery storage page and an FAQ section.")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = create

    with patch.object(svc, "crawl_site", return_value=crawl), patch.object(
        svc, "anthropic_client", return_value=mock_client
    ):
        result = svc.analyze_content(_client())

    assert result["pages_crawled"] == 5
    assert result["entity_coverage_score"] == 50.0
    assert len(result["topics_json"]) == 2
    assert result["content_metrics_json"]["schema_present"] is True
    assert result["content_metrics_json"]["blog_count"] == 2
    assert "battery storage" in result["content_quality_recommendation"].lower()


def _crawl():
    return CrawlResult(
        pages_crawled=4, word_count=1200, h1_count=4, faq_count=0,
        blog_count=1, schema_present=False, text_corpus="Solar panels for homes.",
    )


def test_quality_recommendation_uses_sonnet_not_haiku():
    """This text renders verbatim on /view/[token]/content-plan under "Our
    recommendation" — client-visible prose, so MODEL_NARRATIVE."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text("Add service pages.")
    with patch("app.services.content_analysis_service.anthropic_client", return_value=mock_client), \
            patch("app.services.content_analysis_service.record_llm_call") as rec, \
            patch("app.services.content_analysis_service.pack_context_for", return_value=(None, ())):
        svc._quality_recommendation(_client(), _crawl())

    assert mock_client.messages.create.call_args.kwargs["model"] == svc.MODEL_NARRATIVE
    assert rec.call_args.kwargs["model"] == svc.MODEL_NARRATIVE


def test_topics_and_suggested_content_stay_on_haiku():
    """The siblings did NOT move: topics/entities is internal JSON that never
    reaches a client, and suggested content is admin-only."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _text('{"topics": [], "entities": []}')
    with patch("app.services.content_analysis_service.anthropic_client", return_value=mock_client), \
            patch("app.services.content_analysis_service.record_llm_call") as rec:
        svc._topics_entities(_client(), "corpus text")
    assert mock_client.messages.create.call_args.kwargs["model"] == svc.MODEL
    assert rec.call_args.kwargs["model"] == svc.MODEL

    mock_client.messages.create.return_value = _text('{"suggestions": []}')
    with patch("app.services.content_analysis_service.anthropic_client", return_value=mock_client), \
            patch("app.services.content_analysis_service.record_llm_call") as rec, \
            patch("app.services.content_analysis_service.pack_context_for", return_value=(None, ())):
        svc._suggested_content(_client(), [{"topic": "storage", "status": "missing"}])
    assert mock_client.messages.create.call_args.kwargs["model"] == svc.MODEL
    assert rec.call_args.kwargs["model"] == svc.MODEL
