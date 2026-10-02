from app.core.constants import SCAN_PLATFORMS, SCORE_BANDS, SCORE_WEIGHTS, SCORED_PLATFORMS

# Scanned and reported, but not part of AI Citability (see SCORED_PLATFORMS).
_REPORTED_ONLY = frozenset(SCAN_PLATFORMS) - frozenset(SCORED_PLATFORMS)


def compute_platform_breakdown(
    query_results: list, failed_platforms: list[str] | None = None
) -> dict:
    """Per-platform visibility from client query results only (competitor_id is None).

    Returns {platform: {"visibility": float, "queries": int, "detected": int,
    "status": "ok"|"unavailable", "scored": bool}}. `scored` is False for
    platforms reported but not in AI Citability (SCORED_PLATFORMS). Surfaces
    that do not always answer (Google AI Overviews) also carry
    `answers_shown`: how many of `queries` showed an AI answer at all. A
    question with no answer counts in `queries` as Not seen by AI.
    """
    breakdown: dict = {}
    client_results = [
        r for r in query_results
        if r.competitor_id is None and not getattr(r, "is_control", False)
    ]
    for result in client_results:
        entry = breakdown.setdefault(result.platform, {
            "visibility": 0.0, "queries": 0, "detected": 0, "status": "ok",
            "scored": result.platform in SCORED_PLATFORMS,
        })
        entry["queries"] += 1
        if result.brand_detected:
            entry["detected"] += 1
        shown = getattr(result, "answer_shown", None)
        if shown is True or shown is False:
            entry["answers_shown"] = entry.get("answers_shown", 0) + (1 if shown else 0)
    for entry in breakdown.values():
        entry["visibility"] = round((entry["detected"] / entry["queries"]) * 100, 2)
    for platform in failed_platforms or []:
        breakdown[platform] = {
            "visibility": 0.0, "queries": 0, "detected": 0, "status": "unavailable",
            "scored": platform in SCORED_PLATFORMS,
        }
    return breakdown


def compute_ai_citability(query_results: list, platform_breakdown: dict | None = None) -> float:
    """AI Citability score: equal-weighted mean of per-platform visibility.

    Unavailable platforms are excluded so a provider outage never zeroes the score.
    Reported-only platforms (not in SCORED_PLATFORMS) are excluded so adding a
    surface never moves the score without a SCORE_VERSION bump. Breakdowns
    written before the `scored` flag hold only scored platforms.
    Falls back to a flat detection ratio when no breakdown is supplied (legacy single-platform data).
    """
    if platform_breakdown:
        ok_platforms = [
            e for e in platform_breakdown.values()
            if e["status"] == "ok" and e.get("scored", True)
        ]
        if not ok_platforms:
            return 0.0
        return round(sum(e["visibility"] for e in ok_platforms) / len(ok_platforms), 2)

    client_results = [
        r for r in query_results
        if r.competitor_id is None and not getattr(r, "is_control", False)
        and getattr(r, "platform", None) not in _REPORTED_ONLY
    ]
    if not client_results:
        return 0.0
    detected = sum(1 for r in client_results if r.brand_detected)
    return round((detected / len(client_results)) * 100, 2)


def compute_geo_score(client, ai_citability: float) -> float:
    """Compute overall GEO score from 5 weighted dimensions."""
    technical = 100.0 if client.technical_foundations_verified else 0.0
    structured = 100.0 if client.structured_data_verified else 0.0
    return round(
        ai_citability * SCORE_WEIGHTS["ai_citability"]
        + client.brand_authority_score * SCORE_WEIGHTS["brand_authority"]
        + client.content_quality_score * SCORE_WEIGHTS["content_quality"]
        + technical * SCORE_WEIGHTS["technical_foundations"]
        + structured * SCORE_WEIGHTS["structured_data"],
        2,
    )


def get_score_color(score: float) -> str:
    """3-band traffic-light color, independent of the named bands:
    0-29 red, 30-69 yellow, 70-100 green."""
    floored = int(score)
    if floored >= 70:
        return "green"
    if floored >= 30:
        return "yellow"
    return "red"


def get_score_band(score: float) -> tuple[str, str]:
    """Return (band_name, color) for a given score. The band name still drives
    labels (5 bands); the color is the 3-band traffic light (get_score_color)."""
    floored = int(score)
    for band, (low, high) in SCORE_BANDS.items():
        if low <= floored <= high:
            return band, get_score_color(score)
    return "low", get_score_color(score)


def scores_comparable(current_version: str | None, prev_version: str | None) -> bool:
    """True only when two GeoScore rows came from the SAME known formula version.

    A score delta is only a market signal when the formula behind both numbers
    was identical. When it was not, part of the delta is a methodology artifact
    (v1.3.0 alone moved AI Citability by up to 50 points for the least-visible
    clients), and narrating it as a real movement tells the client a story that
    did not happen.

    NULL means the row predates persisted versioning, so its formula cannot be
    established. Unknown is never treated as "same as current" - two unknown
    rows could be any two versions.
    """
    if current_version is None or prev_version is None:
        return False
    return current_version == prev_version
