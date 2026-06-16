# backend/app/services/content_analysis_service.py
"""Claude-powered content gap + quality analysis over a crawled website.

Topic/entity coverage is INFORMATIONAL ONLY — it never feeds the GEO score.
Content Quality output ASSISTS the manual score; it never auto-writes it.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import structlog

from app.models.client import Client
from app.prompts.content_analysis import (
    build_quality_recommendation,
    build_suggested_content,
    build_topics_entities,
)
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences
from app.services.content_crawler import CrawlResult, crawl_site
from app.services.cost_tracker import record_llm_call

logger = structlog.get_logger()

_MAX_SUGGESTED_TOPICS = 5


def _topics_entities(client: Client, corpus: str) -> dict:
    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": build_topics_entities(client, corpus)}],
    )
    record_llm_call(
        service="content_analysis_topics", model=MODEL, response=response, client_id=client.id
    )
    raw = strip_code_fences(response.content[0].text)
    data = json.loads(raw)
    topics = data.get("topics", []) if isinstance(data, dict) else []
    entities = data.get("entities", []) if isinstance(data, dict) else []
    return {"topics": topics, "entities": entities}


def _quality_recommendation(client: Client, crawl: CrawlResult) -> str:
    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": build_quality_recommendation(client, crawl)}],
    )
    record_llm_call(
        service="content_analysis_quality", model=MODEL, response=response, client_id=client.id
    )
    return response.content[0].text.strip()


def _suggested_content(client: Client, topics: list) -> list:
    missing = [t["topic"] for t in topics if t.get("status") == "missing"][:_MAX_SUGGESTED_TOPICS]
    if not missing:
        return []

    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": build_suggested_content(client, missing)}],
        )
        record_llm_call(
            service="content_analysis_suggested", model=MODEL, response=response, client_id=client.id
        )
        raw = strip_code_fences(response.content[0].text)
        data = json.loads(raw)
        return data.get("suggestions", []) if isinstance(data, dict) else []
    except Exception:
        logger.warning("suggested_content_failed", client_id=str(client.id))
        return []


def _coverage_score(entities: list) -> float:
    if not entities:
        return 0.0
    covered = sum(1 for e in entities if e.get("covered"))
    return round((covered / len(entities)) * 100, 2)


def analyze_content(client: Client) -> dict:
    """Crawl the client's website and return a full content analysis payload."""
    crawl = crawl_site(client.website)
    logger.info(
        "content_crawl_complete",
        client_id=str(client.id),
        pages=crawl.pages_crawled,
        words=crawl.word_count,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        te_future = executor.submit(_topics_entities, client, crawl.text_corpus)
        rec_future = executor.submit(_quality_recommendation, client, crawl)
        topics_entities = te_future.result()
        recommendation = rec_future.result()

    entities = topics_entities["entities"]
    topics = topics_entities["topics"]
    suggestions = _suggested_content(client, topics)
    return {
        "topics_json": topics,
        "entities_json": entities,
        "suggested_content_json": suggestions,
        "entity_coverage_score": _coverage_score(entities),
        "content_metrics_json": {
            "word_count": crawl.word_count,
            "h1_count": crawl.h1_count,
            "faq_count": crawl.faq_count,
            "blog_count": crawl.blog_count,
            "schema_present": crawl.schema_present,
        },
        "content_quality_recommendation": recommendation,
        "pages_crawled": crawl.pages_crawled,
    }
