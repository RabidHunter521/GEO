from app.core.constants import SCORE_BANDS, SCORE_WEIGHTS


def compute_platform_breakdown(
    query_results: list, failed_platforms: list[str] | None = None
) -> dict:
    """Per-platform visibility from client query results only (competitor_id is None).

    Returns {platform: {"visibility": float, "queries": int, "detected": int, "status": "ok"|"unavailable"}}.
    """
    breakdown: dict = {}
    client_results = [r for r in query_results if r.competitor_id is None]
    for result in client_results:
        entry = breakdown.setdefault(
            result.platform, {"visibility": 0.0, "queries": 0, "detected": 0, "status": "ok"}
        )
        entry["queries"] += 1
        if result.brand_detected:
            entry["detected"] += 1
    for entry in breakdown.values():
        entry["visibility"] = round((entry["detected"] / entry["queries"]) * 100, 2)
    for platform in failed_platforms or []:
        breakdown[platform] = {"visibility": 0.0, "queries": 0, "detected": 0, "status": "unavailable"}
    return breakdown


def compute_ai_citability(query_results: list, platform_breakdown: dict | None = None) -> float:
    """AI Citability score: equal-weighted mean of per-platform visibility.

    Unavailable platforms are excluded so a provider outage never zeroes the score.
    Falls back to a flat detection ratio when no breakdown is supplied (legacy single-platform data).
    """
    if platform_breakdown:
        ok_platforms = [e for e in platform_breakdown.values() if e["status"] == "ok"]
        if not ok_platforms:
            return 0.0
        return round(sum(e["visibility"] for e in ok_platforms) / len(ok_platforms), 2)

    client_results = [r for r in query_results if r.competitor_id is None]
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
