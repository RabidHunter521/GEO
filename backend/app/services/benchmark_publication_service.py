# backend/app/services/benchmark_publication_service.py
"""Human-reviewed publication of the SEA AI Visibility Index.

Four states, deliberately not a boolean: draft is machine-generated and
unreviewed, approved is a person attesting to specific bytes, published is
those bytes being served anonymously, and withdrawn closes public access
without deleting the record. A withdrawn edition still has to be answerable
for — it was public once — so the row survives and only the serving stops.

**Publishing never recalculates.** It promotes the payload that was approved,
verified against its hash. The alternative — recomputing at publish time —
would mean the reviewer approved one set of numbers and the world received
another, and nobody would notice.

Thresholds are re-checked at approval, not only at snapshot generation, and the
draft is re-derived and hash-compared so a reviewer can never approve bytes
that no longer describe the data — a retired cohort or a newly approved
snapshot both force a regenerate-and-re-read.

What that re-check does *not* do, deliberately: a client opting out after a
snapshot was approved does not retroactively alter that snapshot. The aggregate
describes a period the client genuinely was a member of, and rewriting it would
mutate an immutable figure someone may already have been shown. Opt-out removes
a client from cohorts computed after the flag is set. That is a forward-looking
guarantee and should be described to clients as one.
"""
import hashlib
import json
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.constants import MIN_METRIC_CONTRIBUTORS
from app.models.benchmark_cohort import BenchmarkCohort
from app.models.benchmark_publication import BenchmarkPublication
from app.models.benchmark_snapshot import BenchmarkSnapshot
from app.schemas.benchmark_comparison import member_count_band
from app.services.benchmark_snapshot_service import BENCHMARK_METRICS

# The packs this edition reports. A metric appears only if it clears the
# privacy gates in EVERY one of them — an index that covers healthcare but
# silently omits F&B invites the reader to assume the omission means zero.
#
# Deliberately a literal, NOT `INDUSTRY_PACK_KEYS`. It was bound to that
# constant once, which made an editorial decision a side effect of the
# engineering registry: registering a fourth pack raised the bar for every
# metric in every edition — nothing could publish until the new pack had its
# own cohort of ten — with no review and no METHODOLOGY_VERSION bump.
# METHODOLOGY_VERSION exists precisely so an edition's definition is stable and
# versioned, so widening the scope is a deliberate edit here plus a bump.
#
# What keeps the pin honest is `packs_covered` in the payload: the reader is
# told the scope rather than inferring it from which cohorts appear, so a pack
# outside the scope is never mistaken for a pack reporting zero.
# `test_required_packs_is_pinned_not_derived_from_the_pack_registry` enforces
# the literal at the source level.
REQUIRED_PACKS: tuple[str, ...] = ("healthcare", "fnb", "local_services")

METHODOLOGY_VERSION = "v1"


class PublicationError(Exception):
    """A publication workflow rule was violated."""


def payload_hash(payload: dict) -> str:
    """SHA-256 over a canonical serialization.

    Sorted keys and fixed separators so an identical payload always hashes
    identically — otherwise dictionary ordering alone would make a re-approval
    look like a content change.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _publishable_snapshots(
    db: Session, period_start: date, period_end: date
) -> list[tuple[BenchmarkCohort, BenchmarkSnapshot]]:
    """Approved, unsuppressed, country-level snapshots for the period.

    `market_area IS NULL` is the small-market exclusion the plan requires: a
    city-level cut of an already-small cohort is the easiest cell in the whole
    dataset to re-identify, so the public index reports country level only.
    """
    return (
        db.query(BenchmarkCohort, BenchmarkSnapshot)
        .join(BenchmarkSnapshot, BenchmarkSnapshot.cohort_id == BenchmarkCohort.id)
        .filter(
            BenchmarkSnapshot.period_start == period_start,
            BenchmarkSnapshot.period_end == period_end,
            BenchmarkSnapshot.approved_at.isnot(None),
            BenchmarkSnapshot.suppressed.is_(False),
            BenchmarkCohort.market_area.is_(None),
            BenchmarkCohort.is_active.is_(True),
        )
        .all()
    )


def build_edition_payload(
    db: Session,
    period_start: date,
    period_end: date,
    methodology_version: str = METHODOLOGY_VERSION,
) -> dict:
    """Assemble the reviewable dataset for one period.

    Returns cohort-level ranges only. No cohort keys, no exact counts, no
    client identifiers, no city cuts. A metric missing from the output means it
    did not clear the gates — never that its value was zero.
    """
    rows = _publishable_snapshots(db, period_start, period_end)

    packs_by_metric: dict[str, set[str]] = {}
    for cohort, snapshot in rows:
        if snapshot.contributing_member_count < MIN_METRIC_CONTRIBUTORS:
            continue
        packs_by_metric.setdefault(snapshot.metric_key, set()).add(cohort.industry_pack)

    qualifying_metrics = {
        metric_key
        for metric_key, packs in packs_by_metric.items()
        if set(REQUIRED_PACKS).issubset(packs)
    }

    entries = []
    for cohort, snapshot in rows:
        if snapshot.metric_key not in qualifying_metrics:
            continue
        if snapshot.contributing_member_count < MIN_METRIC_CONTRIBUTORS:
            continue
        entries.append(
            {
                "industry_pack": cohort.industry_pack,
                "country_code": cohort.country_code,
                "scale_band": cohort.scale_band,
                "coverage_band": cohort.coverage_band,
                "metric_key": snapshot.metric_key,
                "unit": BENCHMARK_METRICS[snapshot.metric_key].unit,
                "p25": float(snapshot.p25),
                "p50": float(snapshot.p50),
                "p75": float(snapshot.p75),
                "member_count_band": member_count_band(snapshot.contributing_member_count),
                "calculation_version": snapshot.calculation_version,
            }
        )

    entries.sort(
        key=lambda entry: (
            entry["industry_pack"],
            entry["country_code"],
            entry["scale_band"],
            entry["metric_key"],
        )
    )
    return {
        "methodology_version": methodology_version,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        # The edition's scope, stated rather than left to be inferred from
        # which cohorts happen to appear. Without it a pinned scope would be a
        # loophole: a reader who knows SeenBy supports a pack, and does not
        # find it here, is back to reading its absence as zero.
        "packs_covered": sorted(REQUIRED_PACKS),
        "metrics_included": sorted(qualifying_metrics),
        "cohorts": entries,
        "notes": [
            "Ranges describe SeenBy clients only and are not a market census.",
            "This edition covers these industries only; an industry not listed "
            "above was not measured for this edition.",
            "A measure is omitted when too few comparable businesses reported it.",
            "Figures are descriptive, not a forecast or a guarantee of results.",
        ],
    }


def create_publication(
    db: Session,
    *,
    slug: str,
    title: str,
    edition: str,
    period_start: date,
    period_end: date,
    generated_by: str,
    methodology_version: str = METHODOLOGY_VERSION,
) -> BenchmarkPublication:
    if db.query(BenchmarkPublication).filter(BenchmarkPublication.slug == slug).first():
        raise PublicationError(f"slug {slug!r} is already in use")

    payload = build_edition_payload(db, period_start, period_end, methodology_version)
    publication = BenchmarkPublication(
        slug=slug,
        title=title,
        edition=edition,
        methodology_version=methodology_version,
        period_start=period_start,
        period_end=period_end,
        status="draft",
        payload=payload,
        payload_hash=payload_hash(payload),
        generated_by=generated_by,
    )
    db.add(publication)
    db.commit()
    return publication


def _get(db: Session, publication_id: uuid.UUID) -> BenchmarkPublication:
    publication = db.get(BenchmarkPublication, publication_id)
    if publication is None:
        raise PublicationError("publication not found")
    return publication


def approve_publication(
    db: Session, publication_id: uuid.UUID, approved_by: str
) -> BenchmarkPublication:
    """Attest to a specific payload, re-checking the privacy gates first."""
    publication = _get(db, publication_id)
    if publication.status != "draft":
        raise PublicationError(f"only a draft can be approved; this is {publication.status}")
    if approved_by == publication.generated_by:
        raise PublicationError(
            "approval must name a different actor than the one that generated the draft"
        )

    # Re-derive from current data. If eligibility moved underneath the draft —
    # a client opted out, a cohort shrank — the reviewer must see the current
    # numbers rather than approve a stale set.
    current = build_edition_payload(
        db, publication.period_start, publication.period_end, publication.methodology_version
    )
    if payload_hash(current) != publication.payload_hash:
        raise PublicationError(
            "the underlying data changed since this draft was generated; "
            "regenerate the draft and review it again"
        )
    if not current["cohorts"]:
        raise PublicationError("nothing clears the privacy thresholds for this period")

    from app.core.time import utcnow

    publication.status = "approved"
    publication.approved_by = approved_by
    publication.approved_at = utcnow()
    db.commit()
    return publication


def publish_publication(db: Session, publication_id: uuid.UUID) -> BenchmarkPublication:
    """Serve the approved bytes. Never recalculates."""
    publication = _get(db, publication_id)
    if publication.status != "approved":
        raise PublicationError(f"only an approved edition can be published; this is {publication.status}")
    if payload_hash(publication.payload) != publication.payload_hash:
        raise PublicationError("stored payload does not match its reviewed hash")

    from app.core.time import utcnow

    publication.status = "published"
    publication.published_at = utcnow()
    db.commit()
    return publication


def withdraw_publication(
    db: Session, publication_id: uuid.UUID, reason: str
) -> BenchmarkPublication:
    """Close public access, keeping the record of what was public."""
    publication = _get(db, publication_id)
    if publication.status not in ("approved", "published"):
        raise PublicationError(f"cannot withdraw a {publication.status} edition")

    from app.core.time import utcnow

    publication.status = "withdrawn"
    publication.withdrawn_at = utcnow()
    publication.withdrawn_reason = reason
    db.commit()
    return publication


def get_published(db: Session, slug: str) -> BenchmarkPublication | None:
    """Only a currently-published edition. Draft, approved and withdrawn all
    return nothing, so a withdrawal takes effect immediately."""
    return (
        db.query(BenchmarkPublication)
        .filter(
            BenchmarkPublication.slug == slug,
            BenchmarkPublication.status == "published",
        )
        .one_or_none()
    )


def list_publications(db: Session) -> list[BenchmarkPublication]:
    return (
        db.query(BenchmarkPublication)
        .order_by(BenchmarkPublication.created_at.desc())
        .all()
    )
