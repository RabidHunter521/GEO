# backend/app/core/constants.py
from typing import Final

SCORE_VERSION: Final = "v1.2.0"  # v1.2.0: Brand Authority & Content Quality are Claude-suggested, admin-reviewed (assisted scoring); weights unchanged

SCORE_WEIGHTS: Final = {
    "ai_citability":         0.40,
    "brand_authority":       0.20,
    "content_quality":       0.20,
    "technical_foundations": 0.10,
    "structured_data":       0.10,
}

# Manual GEO dimensions that support Claude-assisted, admin-reviewed scoring.
DIMENSION_BRAND_AUTHORITY: Final = "brand_authority"
DIMENSION_CONTENT_QUALITY: Final = "content_quality"
ASSESSABLE_DIMENSIONS: Final = (DIMENSION_BRAND_AUTHORITY, DIMENSION_CONTENT_QUALITY)
ASSESSMENT_STATUSES: Final = ("suggested", "accepted", "adjusted")
# Client-facing label replacing "Assessed by SeenBy team" — leads with verifiability.
DIMENSION_EVIDENCE_LABEL: Final = "Based on public evidence · Reviewed by SeenBy"

SCORE_BANDS: Final = {
    "excellent":  (80, 100),
    "good":       (65, 79),
    "fair":       (50, 64),
    "developing": (35, 49),
    "low":        (0,  34),
}

# Score color is a 3-band traffic light keyed off the raw score, independent of
# the named bands above: 0-29 red, 30-69 yellow, 70-100 green.
# See scoring_service.get_score_color. (SCORE_COLORS retained for reference.)
SCORE_COLOR_THRESHOLDS: Final = {"green": 70, "yellow": 30, "red": 0}

SCORE_COLORS: Final = {
    "excellent":  "green",
    "good":       "green",
    "fair":       "yellow",
    "developing": "yellow",
    "low":        "red",
}

# Static query templates per category. {brand}, {competitor}, {industry}, {location}, {city} are filled at runtime.
# 5 per category × 4 categories = up to 20 client queries per platform per scan
# (comparison is capped by the number of competitors, max 5).
# recommendation + local intentionally mix discovery queries ("best X") with
# buyer-journey queries ("how do I choose X", "how much does X cost") to capture
# AI answers across the full consideration funnel, not just top-of-funnel discovery.
QUERY_TEMPLATES: Final = {
    "brand": [
        "Tell me about {brand}",
        "What is {brand} known for?",
        "Is {brand} a good choice?",
        "What services does {brand} offer?",
        "What do people say about {brand}?",
    ],
    "comparison": [
        "{brand} vs {competitor}",
        "Compare {brand} and {competitor}",
        "Is {brand} or {competitor} better?",
        "{brand} vs {competitor}: which should I choose?",
        "How does {brand} compare to {competitor}?",
    ],
    "recommendation": [
        "Best {industry} in {location}",
        "Most trusted {industry} in {location}",
        "How do I choose a {industry} in {location}?",
        "What should I look for in a {industry} in {location}?",
        "How much does a {industry} cost in {location}?",
    ],
    "local": [
        "Best {industry} near me in {city}",
        "Top-rated {industry} in {city}",
        "Affordable {industry} in {city}",
        "How do I find a reliable {industry} in {city}?",
        "Signs I need a {industry} in {city}",
    ],
}

# Competitor query templates (4 per competitor, 1 per category)
COMPETITOR_QUERY_TEMPLATES: Final = {
    "brand":          "Tell me about {competitor}",
    "comparison":     "{competitor} vs {brand}",
    "recommendation": "Best {industry} company in {location}",
    "local":          "Top {industry} in {city}",
}

RAW_RESPONSE_RETENTION_DAYS: Final = 90
# Hard-delete a client's data this long after it was archived (churned).
# CLAUDE.md §8: "Client data archived 6 months after churn, then auto-deleted."
CHURN_DELETE_DAYS: Final = 180
MAX_COMPETITORS: Final = 5
# Benchmark queries deliberately left unoptimized (causal proof) — per client.
MAX_CONTROL_QUERIES: Final = 5

# Referrer domains classified as AI-sourced traffic (GA4 sync). Keys are
# matched against sessionSource/pageReferrer hosts (subdomain-tolerant).
# Extending this dict is the only change needed to track a new AI referrer.
AI_REFERRER_DOMAINS: Final = {
    "chatgpt.com":          "ChatGPT",
    "chat.openai.com":      "ChatGPT",
    "perplexity.ai":        "Perplexity",
    "gemini.google.com":    "Gemini",
    "bard.google.com":      "Gemini",
    "copilot.microsoft.com": "Copilot",
    "claude.ai":            "Claude",
    "you.com":              "You.com",
}
# Default review cadence — drives the "next scan due" reminder on /clients.
# Reminder only; nothing auto-scans (MVP runs on-demand scans only).
DEFAULT_SCAN_CADENCE_DAYS: Final = 30
PLATFORM_GEMINI: Final = "gemini"

SCAN_PLATFORMS: Final = ["chatgpt", "perplexity", "gemini", "claude"]
PLATFORM_LABELS: Final = {
    "chatgpt":    "ChatGPT",
    "perplexity": "Perplexity",
    "gemini":     "Gemini",
    "claude":     "Claude",
}

# AI crawlers checked by the competitor AI-readiness feature. Matches the bot
# list toolkit_service.generate_robots_txt() already allow-lists for clients.
AI_CRAWLER_BOTS: Final = [
    "GPTBot",
    "OAI-SearchBot",
    "PerplexityBot",
    "ClaudeBot",
    "Google-Extended",
    "Amazonbot",
    "Meta-ExternalAgent",
    "Applebot-Extended",
    "DuckAssistBot",
]
# Scan.platform value for multi-platform scans (legacy rows hold a single platform name)
SCAN_PLATFORM_MULTI: Final = "multi"

# A pending/running scan older than this is treated as dead (crashed worker)
# and no longer blocks new scan triggers. A full 4-platform scan takes ~2 min.
ACTIVE_SCAN_STALE_MINUTES: Final = 15

# Win/loss analysis only uses neutral-intent categories: comparison queries name
# the competitor and brand queries name the client, which would poison the signal.
WIN_LOSS_CATEGORIES: Final = ("recommendation", "local")

# Industry benchmarking requires this many scored, non-archived clients (incl. the client)
MIN_BENCHMARK_PEERS: Final = 3

# One static tip per score band — shown when AI Citability change is < 5pts vs previous scan
DIGEST_STATIC_TIPS: Final = {
    "excellent": "Keep publishing content featuring your brand — consistent visibility cements AI recognition over time.",
    "good": "Consider adding a frequently asked questions page — AI models surface structured Q&A content readily.",
    "fair": "Claim your business on Google Business Profile and Apple Maps — AI models draw from structured directory data.",
    "developing": "Your llms.txt file describes your business to AI crawlers. Verify it is live and reflects your core services.",
    "low": "Add your brand name naturally throughout your website copy — AI models recognize brands through consistent contextual mentions.",
}

ALERTS_EMAIL: Final = "contact@seenby.my"

# Remediation loop — the "Flagged -> In progress -> Corrected" status lifecycle
# the SeenBy team works through for hallucinations and competitor-won queries.
# Persisted per client so progress survives across scans (CLAUDE.md client-value
# deliverable). "corrected" is set automatically when a re-scan no longer shows
# the problem, or manually by the admin.
REMEDIATION_STATUSES: Final = ("flagged", "in_progress", "corrected")
REMEDIATION_STATUS_LABELS: Final = {
    "flagged":     "Flagged",
    "in_progress": "In progress",
    "corrected":   "Corrected",
}
REMEDIATION_TYPES: Final = ("hallucination", "content_gap")

# Client view freshness: a visibility score older than this many days surfaces a
# reassuring "next visibility check due ~<date>" line (driven by scan_cadence_days)
# instead of a bare stale date. Reminder framing only — nothing auto-scans (§11).
CLIENT_VIEW_STALE_AFTER_DAYS: Final = 10

# AI referral pipeline estimate defaults (admin-overridable per client). Used to
# turn raw AI-referral visitor counts into a single revenue number for the CEO.
DEFAULT_VISITOR_TO_LEAD_PCT: Final = 2
DEFAULT_LEAD_TO_CUSTOMER_PCT: Final = 20

# Value-at-risk model (rung 2). Floor visibility at 25% so a tiny score can't
# explode the gap multiplier; cap the multiplier at 3x so at-risk is never more
# than 3x captured. Both keep the estimate conservative. See revenue_service.
VALUE_AT_RISK_MIN_VISIBILITY: Final = 0.25
VALUE_AT_RISK_MAX_MULTIPLIER: Final = 3.0

# GEO Action Center — impact estimation and display caps
ACTION_IMPACT_MAX_PER_ACTION: Final = 10.0
ACTION_PRIORITY_BANDS: Final = {
    "high":   (6, 10),
    "medium": (3, 5),
    "low":    (0, 2),
}
MAX_OPEN_ACTIONS: Final = 5
