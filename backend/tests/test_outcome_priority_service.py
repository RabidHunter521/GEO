import pytest

from app.services.outcome_priority_service import PriorityInputs, score_priority


def test_score_priority_returns_medium_band_for_weighted_commercial_opportunity():
    """Catches a changed formula, threshold, or commercial-intent explanation."""
    result = score_priority(
        PriorityInputs(
            commercial_intent=1.0,
            visibility_gap=1.0,
            competitor_advantage=0.8,
            reputation_risk=0.0,
            demand=0.6,
            expected_influence=0.7,
            confidence=0.8,
            effort=0.4,
        )
    )

    assert result.score == 58
    assert result.band == "medium"
    assert "high commercial intent" in result.reasons


@pytest.mark.parametrize(
    ("inputs", "expected_score", "expected_band"),
    [
        (PriorityInputs(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), 0, "low"),
        (PriorityInputs(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0), 50, "medium"),
        (PriorityInputs(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0), 100, "high"),
    ],
)
def test_score_priority_uses_documented_bands(inputs, expected_score, expected_band):
    """Catches a band boundary or score scaling regression."""
    result = score_priority(inputs)

    assert result.score == expected_score
    assert result.band == expected_band


def test_score_priority_clamps_inputs_and_uses_neutral_defaults():
    """Catches out-of-range inputs or missing signals changing prioritization."""
    clamped = score_priority(
        PriorityInputs(
            commercial_intent=2.0,
            visibility_gap=-1.0,
            competitor_advantage=2.0,
            reputation_risk=-1.0,
            demand=2.0,
            expected_influence=-1.0,
            confidence=2.0,
            effort=-1.0,
        )
    )
    neutral = score_priority(PriorityInputs())

    assert clamped.score == 55
    assert neutral.score == 41
    assert neutral.band == "medium"
    assert len(neutral.reasons) <= 3
