"""Deterministic, explainable priority scoring for Outcome Actions."""
from dataclasses import dataclass


PRIORITY_CALCULATION_VERSION = "v1"
NEUTRAL_INPUT_VALUE = 0.5


@dataclass(frozen=True)
class PriorityInputs:
    """Internal scoring signals. Omitted signals default to the neutral midpoint."""

    commercial_intent: float | None = NEUTRAL_INPUT_VALUE
    visibility_gap: float | None = NEUTRAL_INPUT_VALUE
    competitor_advantage: float | None = NEUTRAL_INPUT_VALUE
    reputation_risk: float | None = NEUTRAL_INPUT_VALUE
    demand: float | None = NEUTRAL_INPUT_VALUE
    expected_influence: float | None = NEUTRAL_INPUT_VALUE
    confidence: float | None = NEUTRAL_INPUT_VALUE
    effort: float | None = NEUTRAL_INPUT_VALUE


@dataclass(frozen=True)
class PriorityResult:
    score: int
    band: str
    reasons: tuple[str, ...]


def score_priority(inputs: PriorityInputs) -> PriorityResult:
    """Calculate a 0-100 priority score with concise internal explanations."""
    normalized = normalize_priority_inputs(inputs)
    weighted_signals = (
        0.20 * normalized.commercial_intent
        + 0.15 * normalized.visibility_gap
        + 0.15 * normalized.competitor_advantage
        + 0.20 * normalized.reputation_risk
        + 0.10 * normalized.demand
        + 0.10 * normalized.expected_influence
        + 0.10 * normalized.confidence
    )
    score = int(round(weighted_signals * (1.0 - 0.35 * normalized.effort) * 100))
    band = "high" if score >= 70 else "medium" if score >= 40 else "low"
    return PriorityResult(score=score, band=band, reasons=_priority_reasons(normalized))


def normalize_priority_inputs(inputs: PriorityInputs) -> PriorityInputs:
    """Clamp scoring inputs while treating omitted values as neutral."""
    return PriorityInputs(
        commercial_intent=_clamp(inputs.commercial_intent),
        visibility_gap=_clamp(inputs.visibility_gap),
        competitor_advantage=_clamp(inputs.competitor_advantage),
        reputation_risk=_clamp(inputs.reputation_risk),
        demand=_clamp(inputs.demand),
        expected_influence=_clamp(inputs.expected_influence),
        confidence=_clamp(inputs.confidence),
        effort=_clamp(inputs.effort),
    )


def _clamp(value: float | None) -> float:
    if value is None:
        return NEUTRAL_INPUT_VALUE
    return max(0.0, min(1.0, float(value)))


def _priority_reasons(inputs: PriorityInputs) -> tuple[str, ...]:
    drivers = (
        (0.20 * inputs.commercial_intent, "high commercial intent", inputs.commercial_intent),
        (0.15 * inputs.visibility_gap, "large visibility gap", inputs.visibility_gap),
        (0.15 * inputs.competitor_advantage, "strong competitor advantage", inputs.competitor_advantage),
        (0.20 * inputs.reputation_risk, "material reputation risk", inputs.reputation_risk),
        (0.10 * inputs.demand, "strong buyer demand", inputs.demand),
        (0.10 * inputs.expected_influence, "high expected influence", inputs.expected_influence),
        (0.10 * inputs.confidence, "strong supporting confidence", inputs.confidence),
    )
    return tuple(
        reason
        for _, reason, value in sorted(drivers, key=lambda driver: driver[0], reverse=True)
        if value >= 0.75
    )[:3]
