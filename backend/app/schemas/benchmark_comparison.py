"""Client-safe benchmark comparison contracts (Phase 6 Task 4).

Everything a client can see about a benchmark passes through here, and the
shape is doing privacy work:

* **Bands, not ranks.** A client learns they sit in the top quartile, never
  that they are 3rd of 11. An exact rank in a small cohort combined with a
  published median is most of the way to identifying neighbours.
* **Banded member counts.** "20–49 businesses", never "27". An exact count
  that changes month to month tells an observer exactly when one organization
  joined or left.
* **A suppressed comparison carries a reason and no numbers.** "Not enough
  comparable data yet" is a different statement from "you are performing
  badly", and a client must never read the first as the second.

`BenchmarkComparisonPublic` is a separate model rather than a subclass of the
admin shape, deliberately: subclassing means a field added to the admin model
silently appears on the client surface, which is the exact failure this
separation exists to prevent.
"""
from datetime import date

from pydantic import BaseModel

# Higher is better for every metric currently in the registry, so the band
# names read the same way for all of them.
PERCENTILE_BANDS = ("bottom_quartile", "middle_half", "top_quartile")

# Upper bound None means open-ended.
MEMBER_COUNT_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (10, 19, "10–19"),
    (20, 49, "20–49"),
    (50, 99, "50–99"),
    (100, None, "100+"),
)

# Plain-language labels. CLAUDE.md §2 vocabulary applies — nothing here may say
# cited, citation rate, ranking position, or visibility gap.
METRIC_LABELS: dict[str, str] = {
    "ai_presence_score": "Seen by AI",
    "answer_stability_score": "Answer consistency",
    "accuracy_rate": "Answer accuracy",
    "share_of_source": "Share of sources AI reads",
    "verified_action_rate": "Work verified as complete",
}

SUPPRESSION_MESSAGES: dict[str, str] = {
    "cohort_below_minimum": "Not enough comparable businesses yet to publish a range.",
    "insufficient_contributors": "Not enough comparable businesses have this measure yet.",
    "differencing_risk": "This comparison is withheld to protect other businesses' privacy.",
    "no_cohort": "This business does not yet have a comparable group.",
    "not_eligible": "This business is not yet included in comparisons.",
    "no_client_value": "We do not have this measure for this business in this period.",
}

DEFAULT_CAVEAT = (
    "Describes comparable SeenBy clients over this period. "
    "It is a description of what we measured, not a promise of results."
)


def member_count_band(count: int) -> str:
    for low, high, label in MEMBER_COUNT_BANDS:
        if count >= low and (high is None or count <= high):
            return label
    # Below the floor nothing is publishable at all, so a caller reaching here
    # has already gone wrong; name it rather than inventing a band.
    return "below_threshold"


def percentile_band(value: float, p25: float, p75: float) -> str:
    if value < p25:
        return "bottom_quartile"
    if value > p75:
        return "top_quartile"
    return "middle_half"


class BenchmarkComparison(BaseModel):
    """Admin shape. Carries the cohort key and exact counts for operators."""

    metric_key: str
    metric_label: str
    client_value: float | None = None
    percentile_band: str | None = None
    cohort_label: str
    cohort_key: str | None = None
    eligible_member_count: int | None = None
    contributing_member_count: int | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    period_start: date
    period_end: date
    member_count_band: str | None = None
    calculation_version: str | None = None
    suppressed: bool = False
    suppression_reason: str | None = None
    suppression_message: str | None = None
    caveat: str = DEFAULT_CAVEAT


class BenchmarkComparisonPublic(BaseModel):
    """Client shape. No cohort key, no exact counts, no membership."""

    metric_key: str
    metric_label: str
    client_value: float | None = None
    percentile_band: str | None = None
    cohort_label: str
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    period_start: date
    period_end: date
    member_count_band: str | None = None
    calculation_version: str | None = None
    suppressed: bool = False
    suppression_message: str | None = None
    caveat: str = DEFAULT_CAVEAT

    @classmethod
    def from_comparison(cls, comparison: BenchmarkComparison) -> "BenchmarkComparisonPublic":
        return cls(
            metric_key=comparison.metric_key,
            metric_label=comparison.metric_label,
            client_value=comparison.client_value,
            percentile_band=comparison.percentile_band,
            cohort_label=comparison.cohort_label,
            p25=comparison.p25,
            p50=comparison.p50,
            p75=comparison.p75,
            period_start=comparison.period_start,
            period_end=comparison.period_end,
            member_count_band=comparison.member_count_band,
            calculation_version=comparison.calculation_version,
            suppressed=comparison.suppressed,
            suppression_message=comparison.suppression_message,
            caveat=comparison.caveat,
        )
