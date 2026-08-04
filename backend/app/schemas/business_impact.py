"""Business-impact evidence ladder — the Phase 5 Task 7 aggregation surface.

`ImpactSummary` wraps a `ConversionSummary` (see
`app/schemas/conversion_event.py` / `app/services/conversion_evidence_service.py`)
with a `calculation_version` and a `caveats` list, but keeps the same core
rule as its source: observed, attributed, assisted, and estimated values are
NEVER summed into one number. A caller that wants a headline figure must
pick a level explicitly and say so — this schema will not let that happen
implicitly. See CLAUDE.md's stance on never collapsing distinct evidence
into a single misleading figure, and the Phase 5 Task 7 brief's "never claim
causality from correlation alone."

`ImpactSummaryPublic` is the client-safe projection used by
`app/api/v1/client_view.py`. It carries the same value/currency/window/caveat
shape but omits everything admin-only: there is no `metadata_json`, no
`calculation_method`, no confidence weights, and no admin notes on
`ImpactSummary` in the first place, so the "omit" list here is really about
never adding those fields to the public schema later without a second
thought — see CLAUDE.md section 8.
"""

from datetime import date

from pydantic import BaseModel

CALCULATION_VERSION = "impact_v1"

# Always present regardless of the data — the single non-negotiable warning
# against collapsing evidence levels into a headline number.
_NEVER_SUM_CAVEAT = (
    "Values are separated by evidence level and must not be summed into a "
    "single total"
)


class ImpactSummary(BaseModel):
    """Admin-facing evidence-labeled business impact for one currency + window."""

    observed_value_minor: int
    attributed_value_minor: int
    assisted_value_minor: int
    estimated_value_minor: int
    currency: str
    event_count_by_level: dict[str, int]
    window_start: date | None
    window_end: date | None
    calculation_version: str = CALCULATION_VERSION
    caveats: list[str] = []


class ImpactSummaryPublic(BaseModel):
    """Client-safe projection of `ImpactSummary`.

    Deliberately its own schema (not a subclass or field-aliasing trick) so
    a future admin-only field added to `ImpactSummary` does not leak here by
    accident — the same reasoning `ClientViewOverview` and friends already
    follow for every other client-view schema in this codebase.
    """

    observed_value_minor: int
    attributed_value_minor: int
    assisted_value_minor: int
    estimated_value_minor: int
    currency: str
    event_count_by_level: dict[str, int]
    window_start: date | None
    window_end: date | None
    caveats: list[str] = []

    @classmethod
    def from_summary(cls, summary: ImpactSummary) -> "ImpactSummaryPublic":
        return cls(
            observed_value_minor=summary.observed_value_minor,
            attributed_value_minor=summary.attributed_value_minor,
            assisted_value_minor=summary.assisted_value_minor,
            estimated_value_minor=summary.estimated_value_minor,
            currency=summary.currency,
            event_count_by_level=summary.event_count_by_level,
            window_start=summary.window_start,
            window_end=summary.window_end,
            caveats=summary.caveats,
        )
