from unittest.mock import MagicMock
from app.services.scoring_service import (
    compute_ai_citability,
    compute_geo_score,
    compute_platform_breakdown,
    get_score_band,
    get_score_color,
)


def test_citability_all_detected():
    results = [MagicMock(brand_detected=True, competitor_id=None) for _ in range(8)]
    assert compute_ai_citability(results) == 100.0


def test_citability_none_detected():
    results = [MagicMock(brand_detected=False, competitor_id=None) for _ in range(8)]
    assert compute_ai_citability(results) == 0.0


def test_citability_half_detected():
    results = (
        [MagicMock(brand_detected=True, competitor_id=None) for _ in range(4)]
        + [MagicMock(brand_detected=False, competitor_id=None) for _ in range(4)]
    )
    assert compute_ai_citability(results) == 50.0


def test_citability_ignores_competitor_queries():
    client_results = [MagicMock(brand_detected=True, competitor_id=None) for _ in range(4)]
    competitor_results = [MagicMock(brand_detected=False, competitor_id="some-id") for _ in range(4)]
    assert compute_ai_citability(client_results + competitor_results) == 100.0


def _result(platform, detected, competitor_id=None):
    return MagicMock(platform=platform, brand_detected=detected, competitor_id=competitor_id)


def test_platform_breakdown_per_platform_visibility():
    results = [
        _result("gemini", True), _result("gemini", False),
        _result("claude", True), _result("claude", True),
    ]
    breakdown = compute_platform_breakdown(results)
    assert breakdown["gemini"] == {"visibility": 50.0, "queries": 2, "detected": 1, "status": "ok"}
    assert breakdown["claude"] == {"visibility": 100.0, "queries": 2, "detected": 2, "status": "ok"}


def test_platform_breakdown_ignores_competitor_results():
    results = [
        _result("gemini", True),
        _result("gemini", True, competitor_id="some-id"),
    ]
    breakdown = compute_platform_breakdown(results)
    assert breakdown["gemini"]["queries"] == 1


def test_platform_breakdown_marks_failed_platforms_unavailable():
    breakdown = compute_platform_breakdown([_result("gemini", True)], failed_platforms=["claude"])
    assert breakdown["claude"] == {"visibility": 0.0, "queries": 0, "detected": 0, "status": "unavailable"}


def test_citability_averages_across_platforms():
    breakdown = {
        "gemini": {"visibility": 50.0, "queries": 8, "detected": 4, "status": "ok"},
        "claude": {"visibility": 100.0, "queries": 8, "detected": 8, "status": "ok"},
    }
    assert compute_ai_citability([], breakdown) == 75.0


def test_citability_excludes_unavailable_platforms_from_average():
    breakdown = {
        "gemini": {"visibility": 60.0, "queries": 8, "detected": 5, "status": "ok"},
        "claude": {"visibility": 0.0, "queries": 0, "detected": 0, "status": "unavailable"},
    }
    assert compute_ai_citability([], breakdown) == 60.0


def test_citability_zero_when_all_platforms_unavailable():
    breakdown = {
        "gemini": {"visibility": 0.0, "queries": 0, "detected": 0, "status": "unavailable"},
    }
    assert compute_ai_citability([], breakdown) == 0.0


def test_geo_score_full_weights():
    client = MagicMock(
        brand_authority_score=80,
        content_quality_score=70,
        technical_foundations_verified=True,
        structured_data_verified=True,
    )
    score = compute_geo_score(client, ai_citability=100.0)
    expected = (100.0 * 0.40) + (80 * 0.20) + (70 * 0.20) + (100 * 0.10) + (100 * 0.10)
    assert abs(score - expected) < 0.001


def test_geo_score_unverified_toolkit_contributes_zero():
    client = MagicMock(
        brand_authority_score=0,
        content_quality_score=0,
        technical_foundations_verified=False,
        structured_data_verified=False,
    )
    score = compute_geo_score(client, ai_citability=50.0)
    assert score == 50.0 * 0.40


def test_get_score_band_excellent():
    assert get_score_band(95) == ("excellent", "green")


def test_get_score_band_good():
    assert get_score_band(70) == ("good", "green")


def test_get_score_band_fair():
    assert get_score_band(55) == ("fair", "yellow")


def test_get_score_band_developing():
    assert get_score_band(40) == ("developing", "yellow")


def test_get_score_band_low():
    assert get_score_band(20) == ("low", "red")


def test_get_score_band_boundary_80():
    assert get_score_band(80) == ("excellent", "green")


def test_get_score_band_boundary_65():
    # "good" band starts at 65, but color is the 3-band traffic light:
    # 65 falls in the 30-69 yellow range; green only starts at 70.
    assert get_score_band(65) == ("good", "yellow")


def test_get_score_color_thresholds():
    assert get_score_color(0) == "red"
    assert get_score_color(29) == "red"
    assert get_score_color(30) == "yellow"
    assert get_score_color(69) == "yellow"
    assert get_score_color(70) == "green"
    assert get_score_color(100) == "green"
