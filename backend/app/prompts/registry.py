# backend/app/prompts/registry.py
"""Central registry of all prompt templates.

Maps each service name to its current prompt version and the model it uses.
Services record this via cost_tracker so every cost row is tied to a specific
prompt version — making it easy to see whether a prompt change affected output
quality or token usage.
"""
from app.services.claude_client import MODEL, MODEL_NARRATIVE
from app.services.query_builder import SCAN_QUERY_VERSION
from app.prompts import (
    action_center,
    toolkit,
    content_roadmap,
    content_analysis,
    report,
    digest,
    assessment,
    citability,
)

# service name → {version, model}
REGISTRY: dict[str, dict[str, str]] = {
    "action_center":               {"version": action_center.VERSION,              "model": MODEL_NARRATIVE},
    "toolkit_llms_txt":            {"version": toolkit.LLMS_TXT_VERSION,           "model": MODEL},
    "toolkit_schema_json":         {"version": toolkit.SCHEMA_JSON_VERSION,        "model": MODEL},
    "content_roadmap":             {"version": content_roadmap.ROADMAP_VERSION,    "model": MODEL_NARRATIVE},
    "content_roadmap_article":     {"version": content_roadmap.ARTICLE_VERSION,    "model": MODEL_NARRATIVE},
    "content_analysis_topics":     {"version": content_analysis.TOPICS_ENTITIES_VERSION,    "model": MODEL},
    "content_analysis_quality":    {"version": content_analysis.QUALITY_REC_VERSION,        "model": MODEL},
    "content_analysis_suggested":  {"version": content_analysis.SUGGESTED_CONTENT_VERSION,  "model": MODEL},
    "report_narrative":            {"version": report.VERSION,                     "model": MODEL_NARRATIVE},
    "digest_action":               {"version": digest.VERSION,                     "model": MODEL},
    # Sonnet + web_search: client-visible evidence, on-demand volume — the
    # high-stakes/low-volume case (audit C1; fabricated evidence on Haiku).
    "assessment_brand_authority":  {"version": assessment.BRAND_AUTHORITY_VERSION,  "model": MODEL_NARRATIVE},
    "assessment_content_quality":  {"version": assessment.CONTENT_QUALITY_VERSION,  "model": MODEL_NARRATIVE},
    # Scan platforms — templated visibility queries, not a Claude prompt. "model"
    # is documentation-only; cost rows store the real per-call model from usage.
    "scan_chatgpt":                {"version": SCAN_QUERY_VERSION,                 "model": "gpt-5-mini"},
    "scan_perplexity":             {"version": SCAN_QUERY_VERSION,                 "model": "sonar"},
    "scan_gemini":                 {"version": SCAN_QUERY_VERSION,                 "model": "gemini-2.5-flash-lite"},
    "scan_claude":                 {"version": SCAN_QUERY_VERSION,                 "model": "claude-haiku-4-5-20251001"},
    "citability_suggestions":      {"version": citability.SUGGESTIONS_VERSION,     "model": MODEL},
}


def get_version(service: str) -> str:
    """Return the current prompt version for a service name."""
    return REGISTRY.get(service, {}).get("version", "unknown")
