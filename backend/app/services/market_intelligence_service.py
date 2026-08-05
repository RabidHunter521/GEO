# backend/app/services/market_intelligence_service.py
"""Privacy-safe aggregate trends over the eligible client population.

Answers two questions: what *kind* of source do AI answers lean on in a given
pack and market, and what kind of question is being asked. Both are reported as
categories and bands.

Three suppression rules, all applied per cell:

1. **Minimum contributors.** Fewer than `MIN_METRIC_CONTRIBUTORS` distinct
   clients and the cell says nothing.
2. **Dominant client.** If one client supplies more than 20% of a cell's
   observations, the cell is mostly *that client* wearing a market's clothes.
   Publishing it would attribute one business's source profile to a whole
   category, which is both wrong and identifying.
3. **Eligibility.** The population is exactly the cohort-eligible set, so
   opt-outs, prospects, archived and poorly-measured clients are excluded by
   construction rather than by a filter someone has to remember to add.

No raw prompt text, no domain, and no exact count leaves this module.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app.core.constants import MIN_METRIC_CONTRIBUTORS
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.models.tracked_query import TrackedQuery
from app.schemas.benchmark_cohort import CohortEligibility
from app.schemas.market_intelligence import (
    PackSignalCandidate,
    QueryDemandRow,
    SourceInfluenceRow,
    contributor_band,
    observation_band,
    share_band,
)
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.provenance_service import normalize_domain

CALCULATION_VERSION = "v1"

# A single client may supply at most this share of a cell's observations.
MAX_SINGLE_CLIENT_SHARE = 0.20

# Suffix/keyword heuristics, deliberately explicit rather than clever. Order
# matters: the first match wins.
_DOMAIN_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("government", (".gov", ".gov.my", ".gov.sg", "moh.")),
    ("review", ("trustpilot", "yelp", "google.com/maps", "tripadvisor", "reviews")),
    ("social", ("facebook", "instagram", "linkedin", "tiktok", "twitter", "x.com", "youtube")),
    ("marketplace", ("shopee", "lazada", "grab", "foodpanda", "amazon", "booking.com")),
    ("directory", ("yellowpages", "directory", "listing", "pages.", "findel", "hotfrog")),
    ("news", ("news", "thestar", "nst.", "malaymail", "channelnewsasia", "straitstimes")),
    ("reference", ("wikipedia", "wikidata", "britannica")),
)


def classify_domain_category(domain: str) -> str:
    """Bucket a host into a coarse category.

    Heuristic and labelled as one. An unrecognised host is "other" rather than
    being forced into a category — a wrong bucket would misstate where a
    client's visibility actually comes from.
    """
    if not domain:
        return "other"
    host = domain.lower()
    for category, needles in _DOMAIN_CATEGORY_RULES:
        if any(needle in host for needle in needles):
            return category
    return "other"


def _window(period_start: date, period_end: date) -> tuple[datetime, datetime]:
    return datetime.combine(period_start, time.min), datetime.combine(period_end, time.max)


def _group_key(member: CohortEligibility) -> tuple[str, str] | None:
    if member.spec is None:
        return None
    return member.spec.industry_pack, member.spec.country_code


def _members_by_group(
    members: list[CohortEligibility],
) -> tuple[dict[uuid.UUID, tuple[str, str]], set[tuple[str, str]]]:
    by_client: dict[uuid.UUID, tuple[str, str]] = {}
    groups: set[tuple[str, str]] = set()
    for member in members:
        key = _group_key(member)
        if key is None:
            continue
        by_client[member.client_id] = key
        groups.add(key)
    return by_client, groups


def _finalize(
    row_class,
    *,
    group: tuple[str, str],
    subject_field: str,
    subject: str,
    band_field: str,
    counts_by_client: dict[uuid.UUID, int],
    group_total: int,
    period_start: date,
    period_end: date,
):
    """Apply the suppression rules to one cell and build its row."""
    total = sum(counts_by_client.values())
    contributors = len(counts_by_client)
    pack, country = group

    common = {
        subject_field: subject,
        "industry_pack": pack,
        "country_code": country,
        "period_start": period_start,
        "period_end": period_end,
        "calculation_version": CALCULATION_VERSION,
    }

    if contributors < MIN_METRIC_CONTRIBUTORS:
        return row_class(**common, suppressed=True, suppression_reason="insufficient_contributors")

    if total and max(counts_by_client.values()) / total > MAX_SINGLE_CLIENT_SHARE:
        # This cell is mostly one business wearing a market's clothes.
        return row_class(**common, suppressed=True, suppression_reason="dominant_client")

    return row_class(
        **common,
        **{band_field: share_band(total / group_total if group_total else 0.0)},
        observation_band=observation_band(total),
        contributing_client_band=contributor_band(contributors),
    )


def source_influence(
    db: Session,
    period_start: date,
    period_end: date,
    members: list[CohortEligibility] | None = None,
) -> list[SourceInfluenceRow]:
    """Which categories of source AI answers drew on, by pack and country."""
    members = members if members is not None else eligible_members_for_period(
        db, period_start, period_end
    )
    by_client, groups = _members_by_group(members)
    if not by_client:
        return []

    window_start, window_end = _window(period_start, period_end)
    rows = (
        db.query(Scan.client_id, ScanQuerySource.url, ScanQuerySource.domain)
        .join(ScanQueryResult, ScanQuerySource.scan_query_result_id == ScanQueryResult.id)
        .join(Scan, Scan.id == ScanQueryResult.scan_id)
        .filter(
            Scan.client_id.in_(list(by_client)),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.observed_at >= window_start,
            ScanQueryResult.observed_at <= window_end,
        )
        .all()
    )

    counts: dict[tuple[str, str], dict[str, dict[uuid.UUID, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    group_totals: dict[tuple[str, str], int] = defaultdict(int)
    for client_id, url, domain in rows:
        group = by_client.get(client_id)
        if group is None:
            continue
        category = classify_domain_category(normalize_domain(domain or url or ""))
        counts[group][category][client_id] += 1
        group_totals[group] += 1

    return [
        _finalize(
            SourceInfluenceRow,
            group=group,
            subject_field="domain_category",
            subject=category,
            band_field="influence_band",
            counts_by_client=counts[group][category],
            group_total=group_totals[group],
            period_start=period_start,
            period_end=period_end,
        )
        for group in sorted(groups)
        for category in sorted(counts[group])
    ]


def query_demand(
    db: Session,
    period_start: date,
    period_end: date,
    members: list[CohortEligibility] | None = None,
) -> list[QueryDemandRow]:
    """What kinds of question are being tracked, by pack and country.

    Counts distinct tracked queries, not observations: repeat sampling measures
    the same question again and would otherwise inflate whichever intent
    happens to be sampled most.
    """
    members = members if members is not None else eligible_members_for_period(
        db, period_start, period_end
    )
    by_client, groups = _members_by_group(members)
    if not by_client:
        return []

    window_start, window_end = _window(period_start, period_end)
    rows = (
        db.query(TrackedQuery.client_id, TrackedQuery.intent, TrackedQuery.id)
        .join(ScanQueryResult, ScanQueryResult.tracked_query_id == TrackedQuery.id)
        .filter(
            TrackedQuery.client_id.in_(list(by_client)),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.observed_at >= window_start,
            ScanQueryResult.observed_at <= window_end,
        )
        .distinct()
        .all()
    )

    counts: dict[tuple[str, str], dict[str, dict[uuid.UUID, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    group_totals: dict[tuple[str, str], int] = defaultdict(int)
    for client_id, intent, _tracked_query_id in rows:
        group = by_client.get(client_id)
        if group is None:
            continue
        counts[group][intent][client_id] += 1
        group_totals[group] += 1

    return [
        _finalize(
            QueryDemandRow,
            group=group,
            subject_field="intent_category",
            subject=intent,
            band_field="demand_band",
            counts_by_client=counts[group][intent],
            group_total=group_totals[group],
            period_start=period_start,
            period_end=period_end,
        )
        for group in sorted(groups)
        for intent in sorted(counts[group])
    ]


def export_pack_signals(
    db: Session, period_start: date, period_end: date
) -> list[PackSignalCandidate]:
    """Candidate pack updates for a human to review. Writes nothing.

    Deliberately returns data instead of touching the registry. Changing a pack
    changes what SeenBy asks and how it routes risk; closing that loop
    automatically would let one bad month of aggregates rewrite the product.
    """
    candidates: list[PackSignalCandidate] = []
    members = eligible_members_for_period(db, period_start, period_end)

    for row in source_influence(db, period_start, period_end, members):
        if row.suppressed or row.influence_band not in ("leading", "high"):
            continue
        candidates.append(
            PackSignalCandidate(
                industry_pack=row.industry_pack,
                country_code=row.country_code,
                signal_type="source_category_influence",
                subject=row.domain_category,
                band=row.influence_band,
                period_start=period_start,
                period_end=period_end,
                rationale=(
                    f"{row.domain_category} sources are {row.influence_band} in this market; "
                    "consider whether the pack's trusted-source policy reflects that."
                ),
            )
        )

    for row in query_demand(db, period_start, period_end, members):
        if row.suppressed or row.demand_band not in ("leading", "high"):
            continue
        candidates.append(
            PackSignalCandidate(
                industry_pack=row.industry_pack,
                country_code=row.country_code,
                signal_type="query_intent_demand",
                subject=row.intent_category,
                band=row.demand_band,
                period_start=period_start,
                period_end=period_end,
                rationale=(
                    f"{row.intent_category} questions are {row.demand_band} in this market; "
                    "consider whether the pack's query templates cover them."
                ),
            )
        )

    return candidates
