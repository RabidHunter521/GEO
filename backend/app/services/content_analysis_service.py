# backend/app/services/content_analysis_service.py
"""Claude-powered content gap + quality analysis over a crawled website.

Topic/entity coverage is INFORMATIONAL ONLY — it never feeds the GEO score.
Content Quality output ASSISTS the manual score; it never auto-writes it.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import structlog

from app.models.client import Client
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences
from app.services.content_crawler import CrawlResult, crawl_site

logger = structlog.get_logger()

_CORPUS_SAMPLE_CHARS = 6000  # smaller slice for the quality recommendation call


def _topics_entities(client: Client, corpus: str) -> dict:
    prompt = f"""You analyse how well a business website covers the topics and entities
that AI language models associate with its industry.

Industry: {client.industry}
Business: {client.name}

Below is the visible text crawled from the business website. Based ONLY on this text:
1. List the ~20 most important TOPICS an authoritative {client.industry} website should cover.
   For each, mark status as "strong" (covered in depth), "weak" (mentioned only briefly),
   or "missing" (not covered).
2. List the key named ENTITIES (concepts, services, products, certifications, terms) that AI
   models associate with this industry. For each, mark covered true/false.

Website text:
\"\"\"
{corpus}
\"\"\"

Output ONLY valid JSON, no code fences, in exactly this shape:
{{"topics": [{{"topic": "string", "status": "strong|weak|missing"}}],
  "entities": [{{"entity": "string", "covered": true}}]}}"""

    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = strip_code_fences(response.content[0].text)
    data = json.loads(raw)
    topics = data.get("topics", []) if isinstance(data, dict) else []
    entities = data.get("entities", []) if isinstance(data, dict) else []
    return {"topics": topics, "entities": entities}


def _quality_recommendation(client: Client, crawl: CrawlResult) -> str:
    prompt = f"""You advise on website content quality for AI search visibility.

Business: {client.name} ({client.industry})
Crawl metrics:
- Pages analysed: {crawl.pages_crawled}
- Total word count: {crawl.word_count}
- H1 headings: {crawl.h1_count}
- FAQ sections found: {crawl.faq_count}
- Blog/article pages: {crawl.blog_count}
- Structured data present: {crawl.schema_present}

Sample of the site text:
\"\"\"
{crawl.text_corpus[:_CORPUS_SAMPLE_CHARS]}
\"\"\"

Write 2-3 plain-English sentences recommending how this business could improve its content so AI
systems are more likely to feature it. Be specific and practical. Do not mention scores, tokens,
or technical jargon. Output only the recommendation text."""

    response = anthropic_client().messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


_MAX_SUGGESTED_TOPICS = 5


def _suggested_content(client: Client, topics: list) -> list:
    missing = [t["topic"] for t in topics if t.get("status") == "missing"][:_MAX_SUGGESTED_TOPICS]
    if not missing:
        return []

    topics_list = "\n".join(f"- {topic}" for topic in missing)
    prompt = f"""You suggest content ideas for a {client.industry} business called {client.name}
to help AI search engines feature them more often.

The business does not currently cover these topics on its website:
{topics_list}

For EACH topic above, suggest exactly 2 concrete content/blog post titles the business could
publish, plus a one-sentence rationale for each. The rationale should explain the opportunity in
plain English — for example, framing it as competitors already covering this topic. Do not use
the words "gap", "citation", "mentioned", or "ranking".

Output ONLY valid JSON, no code fences, in exactly this shape:
{{"suggestions": [{{"topic": "string", "title": "string", "rationale": "string"}}]}}"""

    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
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
