"""Business-impact evidence ladder aggregation (Phase 5 Task 7).

`get_impact_summary` is a thin wrapper around
`conversion_evidence_service.summarize_events` — it does not read
`ConversionEvent` rows itself. Per-currency separation, per-evidence-level
totals, and the "no combined total" invariant are all inherited from that
service; this module's only job is to attach a `calculation_version` and a
data-driven set of `caveats` to each `ConversionSummary`, one `ImpactSummary`
per currency.

Caveats are derived from what's actually in the summary, not hardcoded per
call:

- Estimated events present -> flag them as modeled, not measured.
- No observed events -> the reader should not assume anything was directly
  witnessed.
- Attributed events present -> attribution is a configured rule, not a
  guarantee of causation.
- Always -> the never-sum-evidence-levels warning (see
  `app/schemas/business_impact.py`).

Never claim causality from correlation alone: nothing here computes or
implies a causal link between AI visibility and any of these values — that
is a separate, explicitly-labeled subsystem (`causality_service`).
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.schemas.business_impact import CALCULATION_VERSION, ImpactSummary
from app.schemas.conversion_event import ConversionSummary
from app.services import conversion_evidence_service

_NEVER_SUM_CAVEAT = (
    "Values are separated by evidence level and must not be summed into a "
    "single total"
)
_ESTIMATED_CAVEAT = "Estimated values are modeled projections, not measured outcomes"
_NO_OBSERVED_CAVEAT = "No directly observed conversion events in this window"
_ATTRIBUTED_CAVEAT = "Attribution is based on configured source rules"


def get_impact_summary(
    client_id: uuid.UUID,
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ImpactSummary]:
    """One `ImpactSummary` per currency present in the window.

    Mixed currencies are never combined — same rule as
    `conversion_evidence_service.summarize_events`, which this delegates to
    for the actual event aggregation. A client with no conversion events in
    the window gets an empty list, not a zeroed placeholder, since there is
    no currency to hang zeros on.
    """
    summaries = conversion_evidence_service.summarize_events(
        client_id, db, date_from=date_from, date_to=date_to
    )
    return [_to_impact_summary(summary) for summary in summaries]


def _to_impact_summary(summary: ConversionSummary) -> ImpactSummary:
    return ImpactSummary(
        observed_value_minor=summary.observed_value_minor,
        attributed_value_minor=summary.attributed_value_minor,
        assisted_value_minor=summary.assisted_value_minor,
        estimated_value_minor=summary.estimated_value_minor,
        currency=summary.currency,
        event_count_by_level=summary.event_count_by_level,
        window_start=summary.window_start,
        window_end=summary.window_end,
        calculation_version=CALCULATION_VERSION,
        caveats=_caveats_for(summary),
    )


def _caveats_for(summary: ConversionSummary) -> list[str]:
    counts = summary.event_count_by_level
    caveats: list[str] = []
    if counts.get("estimated", 0) > 0:
        caveats.append(_ESTIMATED_CAVEAT)
    if counts.get("observed", 0) == 0:
        caveats.append(_NO_OBSERVED_CAVEAT)
    if counts.get("attributed", 0) > 0:
        caveats.append(_ATTRIBUTED_CAVEAT)
    # Always last: the one warning that applies unconditionally.
    caveats.append(_NEVER_SUM_CAVEAT)
    return caveats
