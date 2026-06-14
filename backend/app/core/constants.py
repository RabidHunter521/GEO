# backend/app/core/constants.py
from typing import Final

SCORE_VERSION: Final = "v1.1.0"  # v1.1.0: AI Citability averages across enabled platforms

SCORE_WEIGHTS: Final = {
    "ai_citability":         0.40,
    "brand_authority":       0.20,
    "content_quality":       0.20,
    "technical_foundations": 0.10,
    "structured_data":       0.10,
}

SCORE_BANDS: Final = {
    "excellent":  (80, 100),
    "good":       (65, 79),
    "fair":       (50, 64),
    "developing": (35, 49),
    "low":        (0,  34),
}

SCORE_COLORS: Final = {
    "excellent":  "green",
    "good":       "green",
    "fair":       "yellow",
    "developing": "yellow",
    "low":        "red",
}

# Static query templates per category. {brand}, {competitor}, {industry}, {location}, {city} are filled at runtime.
QUERY_TEMPLATES: Final = {
    "brand": [
        "Tell me about {brand}",
        "What is {brand} known for?",
    ],
    "comparison": [
        "{brand} vs {competitor}",
        "Compare {brand} and {competitor}",
    ],
    "recommendation": [
        "Best {industry} in {location}",
        "Top {industry} in {location}",
    ],
    "local": [
        "Best {industry} near me in {city}",
        "{industry} services in {city}",
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
PLATFORM_GEMINI: Final = "gemini"

SCAN_PLATFORMS: Final = ["chatgpt", "perplexity", "gemini", "claude"]
PLATFORM_LABELS: Final = {
    "chatgpt":    "ChatGPT",
    "perplexity": "Perplexity",
    "gemini":     "Gemini",
    "claude":     "Claude",
}
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

# GEO Action Center — impact estimation and display caps
ACTION_IMPACT_MAX_PER_ACTION: Final = 10.0
ACTION_PRIORITY_BANDS: Final = {
    "high":   (6, 10),
    "medium": (3, 5),
    "low":    (0, 2),
}
MAX_OPEN_ACTIONS: Final = 5
