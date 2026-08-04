# backend/app/prompts/content_analysis.py
"""Prompt templates for content gap and quality analysis."""
from app.models.client import Client
from app.prompts.industry_pack import build_pack_context
from app.prompts.language import LANGUAGE_RULES

# Unversioned by this change: topic/entity extraction emits internal JSON that
# never reaches a client, so it carries no language rules to share.
TOPICS_ENTITIES_VERSION = "v1"
# v3: industry pack context — the recommendation now speaks in the client's
# industry vocabulary and may not invent facts outside the approved set.
QUALITY_REC_VERSION = "v3"
# v3: industry pack context (see QUALITY_REC_VERSION).
SUGGESTED_CONTENT_VERSION = "v3"


def build_topics_entities(client: Client, corpus: str) -> str:
    return f"""You analyse how well a business website covers the topics and entities
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


def build_quality_recommendation(client: Client, crawl, pack=None, facts=()) -> str:
    return f"""You advise on website content quality for AI search visibility.

Business: {client.name} ({client.industry})
{build_pack_context(client, pack, facts)}
Crawl metrics:
- Pages analysed: {crawl.pages_crawled}
- Total word count: {crawl.word_count}
- H1 headings: {crawl.h1_count}
- FAQ sections found: {crawl.faq_count}
- Blog/article pages: {crawl.blog_count}
- Structured data present: {crawl.schema_present}

Sample of the site text:
\"\"\"
{crawl.text_corpus[:6000]}
\"\"\"

Write 2-3 plain-English sentences recommending how this business could improve its content so AI
systems are more likely to feature it. Be specific and practical. Do not mention scores, tokens,
or technical jargon. {LANGUAGE_RULES}
Also avoid "outrank", "outranks", "ranking" and "gap" — if a competitor is favored by AI answers
today, say they "currently appear instead of" this business. Output only the recommendation text."""


def build_suggested_content(
    client: Client, missing_topics: list[str], pack=None, facts=()
) -> str:
    topics_list = "\n".join(f"- {topic}" for topic in missing_topics)
    return f"""You suggest content ideas for a {client.industry} business called {client.name}
to help AI search engines feature them more often.
{build_pack_context(client, pack, facts)}

The business does not currently cover these topics on its website:
{topics_list}

For EACH topic above, suggest exactly 2 concrete content/blog post titles the business could
publish, plus a one-sentence rationale for each. The rationale should explain the opportunity in
plain English — for example, framing it as competitors already covering this topic.
{LANGUAGE_RULES}
Also avoid the words "gap" and "ranking".

Output ONLY valid JSON, no code fences, in exactly this shape:
{{"suggestions": [{{"topic": "string", "title": "string", "rationale": "string"}}]}}"""
