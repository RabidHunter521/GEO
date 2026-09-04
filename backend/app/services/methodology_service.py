"""Client-facing measurement methodology.

This is the shipped counterpart to docs/methodology.md: the version a client can
actually read, served on the share-token view and condensed into the PDF report.

Every number here is derived from app.core.constants, never retyped. A weight
change therefore updates the published methodology in the same commit that
changes the score - the failure mode this module exists to prevent is a
published methodology that quietly describes a formula the product no longer
uses.

Language follows CLAUDE.md section 2: "Seen by AI", never "cited"/"mentioned".
"""
from app.core.constants import (
    DIMENSION_EVIDENCE_LABEL,
    SCAN_PLATFORMS,
    SCORE_DISPLAY_LABEL,
    SCORE_VERSION,
    SCORE_WEIGHTS,
    PLATFORM_LABELS,
)

# How each dimension is produced. "measured" dimensions come from the scan or a
# live check of the client's own site; "reviewed" dimensions are researched from
# public evidence and signed off by a person before they count.
_DIMENSIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "ai_citability",
        "AI Citability",
        "measured",
        "How often your brand is Seen by AI across the buyer questions we track, "
        "averaged evenly across the AI platforms you have switched on.",
    ),
    (
        "brand_authority",
        "Brand Authority",
        "reviewed",
        "How well your business is established across the public sources AI "
        "systems read - directories, reviews, and profiles. Researched from "
        "public evidence and reviewed by a person before it counts.",
    ),
    (
        "content_quality",
        "Content Quality",
        "reviewed",
        "How completely your own site answers the questions buyers ask, based on "
        "a crawl of your pages. Researched from public evidence and reviewed by "
        "a person before it counts.",
    ),
    (
        "technical_foundations",
        "Technical Foundations",
        "measured",
        "Whether your robots.txt lets AI crawlers read your site. Verified by "
        "fetching the file from your domain. This is either met or not met - "
        "there is no partial credit.",
    ),
    (
        "structured_data",
        "Structured Data",
        "measured",
        "Whether your pages carry structured data describing your business. "
        "Verified by fetching your site. This is either met or not met - there "
        "is no partial credit.",
    ),
)

_LIMITS: tuple[str, ...] = (
    "The questions we track are a monitored sample chosen so results can be "
    "compared over time. They are not every question a buyer might ask.",
    "AI answers vary between runs, platforms, model versions, and locations. A "
    "single change is evidence, not proof of a lasting shift.",
    f"{SCORE_DISPLAY_LABEL} is a leading indicator. It is not a measure of "
    "confirmed traffic, leads, or revenue.",
    "Coverage is limited to the AI platforms enabled for you and what their "
    "APIs return, which can differ from what you see in a consumer app.",
)


def _dimension_rows() -> list[dict]:
    rows = []
    for key, label, basis, description in _DIMENSIONS:
        rows.append({
            "key": key,
            "label": label,
            "weight_percent": round(SCORE_WEIGHTS[key] * 100),
            "basis": basis,
            "description": description,
            "evidence_label": DIMENSION_EVIDENCE_LABEL if basis == "reviewed" else None,
        })
    return rows


def build_methodology(enabled_platforms: list[str] | None = None) -> dict:
    """Payload for the client-facing methodology page and the PDF section."""
    platforms = [p for p in (enabled_platforms or []) if p in SCAN_PLATFORMS]
    rows = _dimension_rows()
    measured_weight = sum(r["weight_percent"] for r in rows if r["basis"] == "measured")
    reviewed_weight = sum(r["weight_percent"] for r in rows if r["basis"] == "reviewed")
    return {
        "score_label": SCORE_DISPLAY_LABEL,
        "score_version": SCORE_VERSION,
        "dimensions": rows,
        "measured_weight_percent": measured_weight,
        "reviewed_weight_percent": reviewed_weight,
        "platforms": [PLATFORM_LABELS.get(p, p.title()) for p in platforms],
        "limitations": list(_LIMITS),
        # Stated plainly because it is the honest answer to "why did my score
        # move?" and because a client who finds it out later stops trusting the
        # rest of the report.
        "version_policy": (
            f"Scores carry the version of the method that produced them (now "
            f"{SCORE_VERSION}). When we improve the method, past scores keep the "
            "values they were given rather than being rewritten. Where a score "
            "and the one before it came from different versions, we tell you, "
            "and we do not present the difference as a change in your standing."
        ),
    }
