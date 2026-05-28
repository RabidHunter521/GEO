from app.core.constants import SCORE_BANDS, SCORE_COLORS, SCORE_WEIGHTS


def compute_ai_citability(query_results: list) -> float:
    """Compute AI Citability score from client query results only (competitor_id is None)."""
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


def get_score_band(score: float) -> tuple[str, str]:
    """Return (band_name, color) for a given score."""
    floored = int(score)
    for band, (low, high) in SCORE_BANDS.items():
        if low <= floored <= high:
            return band, SCORE_COLORS[band]
    return "low", SCORE_COLORS["low"]
