"""Aggregate market-intelligence contracts (Phase 6 Task 8).

Internal in this release. Nothing here is client-facing and nothing here is
public — publishing any of it requires the Task 7 review workflow.

Two shapes, one discipline: **categories and bands, never values**. The rows
report which *kind* of source AI answers lean on and roughly how much, not
which domains or how many times. A raw domain list from a small cohort is
close to a client list — a clinic's own site, its two directory listings, its
review profile — and a raw count moving month to month says when one client
joined or left.
"""
from datetime import date

from pydantic import BaseModel

# Share of a group's observations. Ordered widest-first for lookup.
SHARE_BANDS: tuple[tuple[float, str], ...] = (
    (0.25, "leading"),
    (0.10, "high"),
    (0.03, "moderate"),
    (0.0, "low"),
)

# Banded observation volumes. Same reasoning as member-count bands: an exact
# count is a timestamp for portfolio changes.
OBSERVATION_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (1, 49, "under_50"),
    (50, 199, "50_199"),
    (200, 999, "200_999"),
    (1000, None, "1000_plus"),
)

CONTRIBUTOR_BANDS: tuple[tuple[int, int | None, str], ...] = (
    (5, 9, "5–9"),
    (10, 19, "10–19"),
    (20, 49, "20–49"),
    (50, None, "50+"),
)

# Heuristic, and labelled as one. An unrecognised host is "other", never
# guessed into a category that would misstate where a client's visibility
# comes from.
DOMAIN_CATEGORIES = (
    "directory",
    "review",
    "social",
    "news",
    "marketplace",
    "government",
    "reference",
    "own_or_peer_site",
    "other",
)


def share_band(share: float) -> str:
    for threshold, label in SHARE_BANDS:
        if share >= threshold:
            return label
    return "low"


def _band(value: int, bands) -> str:
    for low, high, label in bands:
        if value >= low and (high is None or value <= high):
            return label
    return "below_threshold"


def observation_band(count: int) -> str:
    return _band(count, OBSERVATION_BANDS)


def contributor_band(count: int) -> str:
    return _band(count, CONTRIBUTOR_BANDS)


class MarketIntelligenceRow(BaseModel):
    """Fields common to both aggregates."""

    industry_pack: str
    country_code: str
    period_start: date
    period_end: date
    observation_band: str | None = None
    contributing_client_band: str | None = None
    calculation_version: str
    suppressed: bool = False
    suppression_reason: str | None = None


class SourceInfluenceRow(MarketIntelligenceRow):
    domain_category: str
    influence_band: str | None = None


class QueryDemandRow(MarketIntelligenceRow):
    intent_category: str
    demand_band: str | None = None


class PackSignalCandidate(BaseModel):
    """A suggestion for a pack maintainer. Never applied automatically.

    Phase 6 output describes what the market looks like; changing a pack
    changes what SeenBy asks and how it routes risk. A pipeline that edited
    prompts or risk rules from its own aggregates would close that loop with
    no human in it, and a bad month of data would rewrite the product.
    """

    industry_pack: str
    country_code: str
    signal_type: str
    subject: str
    band: str
    period_start: date
    period_end: date
    rationale: str
    requires_human_approval: bool = True
