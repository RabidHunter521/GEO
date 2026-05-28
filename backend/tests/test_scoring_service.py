from unittest.mock import MagicMock
from app.services.scoring_service import (
    compute_ai_citability,
    compute_geo_score,
    get_score_band,
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
    assert get_score_band(65) == ("good", "green")
