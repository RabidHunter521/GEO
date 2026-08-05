"""Phase 6 Task 7 — the human review gate on the public index.

The tests that matter here are the ones proving review means something:
approval attests to specific bytes, publishing serves those exact bytes, and a
withdrawal closes access without destroying the record of what was said.
"""
from datetime import date, datetime

import pytest

from app.core.constants import MIN_METRIC_CONTRIBUTORS
from app.models.benchmark_publication import (
    ApprovedPublicationImmutableError,
    BenchmarkPublication,
)
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_publication_service import (
    METHODOLOGY_VERSION,
    PublicationError,
    approve_publication,
    build_edition_payload,
    create_publication,
    get_published,
    payload_hash,
    publish_publication,
    withdraw_publication,
)
from app.services.benchmark_snapshot_service import generate_ladder_snapshots

from tests.test_benchmark_snapshot_service import (
    PERIOD_END,
    PERIOD_START,
    make_measured_client,
    spec_for,
)

APPROVED_AT = datetime(2026, 8, 1, 9, 0, 0)


def publish_cohort_for(db, pack, *, count=10, score=55.0, subcategory=None):
    """Approve a country-level cohort for one pack."""
    for _ in range(count):
        client = make_measured_client(db, ai_citability=score, subcategory=subcategory)
        client.industry_pack = pack
        db.commit()
    members = eligible_members_for_period(db, PERIOD_START, PERIOD_END)
    spec = spec_for(industry_pack=pack, subcategory=subcategory, market_area=None)
    for snapshot in generate_ladder_snapshots(
        db, spec, members, "ai_presence_score", PERIOD_START, PERIOD_END
    ):
        # Only approve what is not already approved. Re-assigning the same
        # value still marks the attribute dirty on an expired instance, and the
        # immutability guard correctly rejects the resulting UPDATE.
        if not snapshot.suppressed and snapshot.approved_at is None:
            snapshot.approved_at = APPROVED_AT
    db.commit()


def all_three_packs(db):
    for pack in ("healthcare", "fnb", "local_services"):
        publish_cohort_for(db, pack)


def draft(db, **overrides):
    fields = dict(
        slug="sea-ai-visibility-index-2026-07",
        title="SEA AI Visibility Index",
        edition="2026-07",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        generated_by="generator@seenby.my",
    )
    fields.update(overrides)
    return create_publication(db, **fields)


# --- payload construction -----------------------------------------------------


def test_payload_omits_every_client_identifier(db):
    all_three_packs(db)
    payload = build_edition_payload(db, PERIOD_START, PERIOD_END)

    serialized = str(payload)
    for forbidden in ("client_id", "cohort_key", "cohort_id", "eligible_member_count", "@"):
        assert forbidden not in serialized


def test_payload_reports_bands_not_counts(db):
    all_three_packs(db)
    entry = build_edition_payload(db, PERIOD_START, PERIOD_END)["cohorts"][0]

    assert entry["member_count_band"] == "10–19"
    assert "contributing_member_count" not in entry
    assert "member_count" not in entry


def test_payload_excludes_small_market_cuts(db):
    """City-level cells of an already-small cohort are the easiest to
    re-identify, so the public index reports country level only."""
    all_three_packs(db)
    payload = build_edition_payload(db, PERIOD_START, PERIOD_END)

    for entry in payload["cohorts"]:
        assert "market_area" not in entry
    assert payload["cohorts"]


def test_a_metric_missing_from_one_pack_is_excluded_entirely(db):
    """An index covering healthcare but silently omitting F&B invites the
    reader to assume the omission means zero."""
    publish_cohort_for(db, "healthcare")
    publish_cohort_for(db, "fnb")
    # local_services never reaches the threshold.
    publish_cohort_for(db, "local_services", count=4)

    payload = build_edition_payload(db, PERIOD_START, PERIOD_END)
    assert payload["metrics_included"] == []
    assert payload["cohorts"] == []


def test_payload_states_it_is_descriptive_not_a_guarantee(db):
    all_three_packs(db)
    notes = " ".join(build_edition_payload(db, PERIOD_START, PERIOD_END)["notes"]).lower()
    assert "guarantee" in notes
    assert "not a market census" in notes


def test_payload_hash_is_stable_across_key_order(db):
    first = {"b": 2, "a": 1}
    second = {"a": 1, "b": 2}
    assert payload_hash(first) == payload_hash(second)


# --- workflow -----------------------------------------------------------------


def test_draft_starts_unapproved(db):
    all_three_packs(db)
    publication = draft(db)

    assert publication.status == "draft"
    assert publication.approved_at is None
    assert publication.payload_hash == payload_hash(publication.payload)


def test_duplicate_slug_is_rejected(db):
    all_three_packs(db)
    draft(db)
    with pytest.raises(PublicationError, match="already in use"):
        draft(db)


def test_approval_requires_a_different_actor(db):
    all_three_packs(db)
    publication = draft(db)

    with pytest.raises(PublicationError, match="different actor"):
        approve_publication(db, publication.id, "generator@seenby.my")


def test_approval_by_a_second_actor_succeeds(db):
    all_three_packs(db)
    publication = draft(db)
    approved = approve_publication(db, publication.id, "reviewer@seenby.my")

    assert approved.status == "approved"
    assert approved.approved_by == "reviewer@seenby.my"
    assert approved.approved_at is not None


def test_approval_rejects_a_draft_whose_underlying_data_moved(db):
    """A reviewer must never approve bytes that no longer describe the data.

    Retiring a cohort between generation and approval changes what the edition
    would contain, so the draft has to be regenerated and re-read rather than
    rubber-stamped.
    """
    all_three_packs(db)
    publication = draft(db)

    from app.models.benchmark_cohort import BenchmarkCohort

    cohort = (
        db.query(BenchmarkCohort).filter(BenchmarkCohort.industry_pack == "healthcare").first()
    )
    cohort.is_active = False
    db.commit()

    with pytest.raises(PublicationError, match="underlying data changed"):
        approve_publication(db, publication.id, "reviewer@seenby.my")


def test_opting_out_does_not_retroactively_rewrite_an_approved_period(db):
    """Opt-out is forward-looking, and that is the honest behaviour.

    An approved snapshot describes a period the client genuinely was a member
    of. Retroactively removing them would mutate an immutable aggregate and
    silently change a figure someone may already have been shown. Opting out
    removes the client from cohorts computed *after* the flag is set.
    """
    all_three_packs(db)
    publication = draft(db)
    before = dict(publication.payload)

    from app.models.client import Client

    client = db.query(Client).filter(Client.industry_pack == "healthcare").first()
    client.benchmark_opt_out = True
    db.commit()

    approved = approve_publication(db, publication.id, "reviewer@seenby.my")
    assert approved.payload == before


def test_a_period_with_nothing_publishable_cannot_be_approved(db):
    publish_cohort_for(db, "healthcare", count=4)
    publication = draft(db)

    with pytest.raises(PublicationError, match="privacy thresholds"):
        approve_publication(db, publication.id, "reviewer@seenby.my")


def test_only_a_draft_can_be_approved(db):
    all_three_packs(db)
    publication = draft(db)
    approve_publication(db, publication.id, "reviewer@seenby.my")

    with pytest.raises(PublicationError, match="only a draft"):
        approve_publication(db, publication.id, "another@seenby.my")


def test_publishing_promotes_the_reviewed_bytes(db):
    all_three_packs(db)
    publication = draft(db)
    approved = approve_publication(db, publication.id, "reviewer@seenby.my")
    reviewed_hash = approved.payload_hash

    published = publish_publication(db, publication.id)
    assert published.status == "published"
    assert published.published_at is not None
    assert published.payload_hash == reviewed_hash
    assert payload_hash(published.payload) == reviewed_hash


def test_publishing_does_not_recalculate(db):
    """The reviewer approved one set of numbers; the world must receive those."""
    all_three_packs(db)
    publication = draft(db)
    approve_publication(db, publication.id, "reviewer@seenby.my")
    before = dict(publication.payload)

    publish_cohort_for(db, "healthcare", count=10, score=99.0)
    published = publish_publication(db, publication.id)

    assert published.payload == before


def test_an_unapproved_draft_cannot_be_published(db):
    all_three_packs(db)
    publication = draft(db)
    with pytest.raises(PublicationError, match="only an approved edition"):
        publish_publication(db, publication.id)


# --- immutability and withdrawal ----------------------------------------------


def test_approved_payload_cannot_be_edited(db):
    all_three_packs(db)
    publication = draft(db)
    approve_publication(db, publication.id, "reviewer@seenby.my")

    publication.payload = {"tampered": True}
    with pytest.raises(ApprovedPublicationImmutableError):
        db.commit()


def test_approved_slug_and_period_are_frozen(db):
    all_three_packs(db)
    publication = draft(db)
    approve_publication(db, publication.id, "reviewer@seenby.my")

    publication.period_end = date(2026, 8, 31)
    with pytest.raises(ApprovedPublicationImmutableError):
        db.commit()


def test_a_draft_can_still_be_corrected(db):
    all_three_packs(db)
    publication = draft(db)
    publication.title = "SEA AI Visibility Index — corrected"
    db.commit()
    assert "corrected" in publication.title


def test_withdrawal_closes_access_without_deleting_the_record(db):
    all_three_packs(db)
    publication = draft(db)
    approve_publication(db, publication.id, "reviewer@seenby.my")
    publish_publication(db, publication.id)
    assert get_published(db, publication.slug) is not None

    withdrawn = withdraw_publication(db, publication.id, "figures restated")

    assert withdrawn.status == "withdrawn"
    assert withdrawn.withdrawn_reason == "figures restated"
    assert get_published(db, publication.slug) is None
    assert db.query(BenchmarkPublication).count() == 1
    assert withdrawn.payload  # the record of what was public survives


def test_a_draft_cannot_be_withdrawn(db):
    all_three_packs(db)
    publication = draft(db)
    with pytest.raises(PublicationError, match="cannot withdraw a draft"):
        withdraw_publication(db, publication.id, "no reason")


def test_get_published_ignores_every_non_published_state(db):
    all_three_packs(db)
    publication = draft(db)
    assert get_published(db, publication.slug) is None

    approve_publication(db, publication.id, "reviewer@seenby.my")
    assert get_published(db, publication.slug) is None


def test_methodology_version_travels_with_the_payload(db):
    all_three_packs(db)
    publication = draft(db)
    assert publication.payload["methodology_version"] == METHODOLOGY_VERSION
    assert publication.methodology_version == METHODOLOGY_VERSION


def test_contributor_floor_is_enforced_in_the_payload(db):
    all_three_packs(db)
    payload = build_edition_payload(db, PERIOD_START, PERIOD_END)
    assert payload["cohorts"]
    # Every published band starts at or above the contributor floor.
    assert MIN_METRIC_CONTRIBUTORS <= 10
    for entry in payload["cohorts"]:
        assert entry["member_count_band"] != "below_threshold"
