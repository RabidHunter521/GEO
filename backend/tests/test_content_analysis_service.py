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
    def create(model, max_tokens, messages):
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
