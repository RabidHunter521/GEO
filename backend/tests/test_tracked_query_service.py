"""Service-level invariants for the tracked-query portfolio: normalization,
duplicate prevention, cross-client isolation, location ownership, archive
semantics, stable ordering, and the priority scoring contract.
"""

import time

import pytest


def _make_client(db, name="Acme Dental"):
    from app.models.client import Client

    client = Client(
        name=name,
        website=f"https://{name.lower().replace(' ', '')}.example.com",
        industry="Dental clinic",
        contact_email="hello@example.com",
    )
    db.add(client)
    db.commit()
    return client


def _make_location(db, client_id, name="Orchard Clinic"):
    from app.services.business_location_service import create_location
    from app.schemas.business_location import BusinessLocationCreate

    return create_location(
        client_id,
        BusinessLocationCreate(name=name, country="SG", latitude=1.3048, longitude=103.8318),
        db,
    )


def _payload(text="Best dentist in KL", **overrides):
    from app.schemas.tracked_query import TrackedQueryCreate

    body = {"text": text, "source": "manual", "intent": "recommendation"}
    body.update(overrides)
    return TrackedQueryCreate(**body)


# --- Normalization -----------------------------------------------------


def test_normalize_query_text_collapses_whitespace_nfc_and_lowercases():
    from app.services.tracked_query_service import normalize_query_text

    # NFKC/NFC distinction: full-width space + mixed case + irregular spacing.
    raw = "  Best   Dentist\tin\nKL  "
    assert normalize_query_text(raw) == "best dentist in kl"


def test_normalize_query_text_applies_unicode_nfc():
    from app.services.tracked_query_service import normalize_query_text

    # "é" as combining sequence (e + U+0301) vs precomposed (U+00E9) must
    # normalize identically under NFC.
    decomposed = "café"
    precomposed = "café"
    assert normalize_query_text(decomposed) == normalize_query_text(precomposed)


# --- Duplicate prevention -----------------------------------------------


def test_create_rejects_duplicate_normalized_text_at_brand_scope(db):
    from app.services.tracked_query_service import create_tracked_query, TrackedQueryDuplicateError

    account = _make_client(db)
    create_tracked_query(account.id, _payload("Best Dentist in KL"), db)

    with pytest.raises(TrackedQueryDuplicateError):
        create_tracked_query(account.id, _payload("  best   dentist in kl  "), db)


def test_create_allows_same_text_across_different_clients(db):
    from app.services.tracked_query_service import create_tracked_query

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")

    first = create_tracked_query(account_a.id, _payload("Best dentist"), db)
    second = create_tracked_query(account_b.id, _payload("Best dentist"), db)

    assert first.id != second.id


def test_create_allows_same_text_at_brand_and_location_scope(db):
    """A brand-level (location_id NULL) and a location-level row never
    collide through a shared NULL — the model's two partial unique indexes
    exist precisely so this does not raise."""
    from app.services.tracked_query_service import create_tracked_query

    account = _make_client(db)
    location = _make_location(db, account.id)

    brand_level = create_tracked_query(account.id, _payload("Best dentist"), db)
    location_level = create_tracked_query(
        account.id, _payload("Best dentist", location_id=location.id), db
    )

    assert brand_level.location_id is None
    assert location_level.location_id == location.id


def test_create_rejects_duplicate_within_same_location_scope(db):
    from app.services.tracked_query_service import create_tracked_query, TrackedQueryDuplicateError

    account = _make_client(db)
    location = _make_location(db, account.id)
    create_tracked_query(account.id, _payload("Best dentist", location_id=location.id), db)

    with pytest.raises(TrackedQueryDuplicateError):
        create_tracked_query(account.id, _payload("BEST DENTIST", location_id=location.id), db)


def test_patch_rejects_rename_into_an_existing_duplicate(db):
    from app.services.tracked_query_service import create_tracked_query, patch_tracked_query, TrackedQueryDuplicateError
    from app.schemas.tracked_query import TrackedQueryPatch

    account = _make_client(db)
    create_tracked_query(account.id, _payload("Best dentist"), db)
    other = create_tracked_query(account.id, _payload("Cheap dentist"), db)

    with pytest.raises(TrackedQueryDuplicateError):
        patch_tracked_query(other, TrackedQueryPatch(text="Best dentist"), db)


def test_patch_rejects_moving_into_a_location_that_already_has_the_same_text(db):
    from app.services.tracked_query_service import create_tracked_query, patch_tracked_query, TrackedQueryDuplicateError
    from app.schemas.tracked_query import TrackedQueryPatch

    account = _make_client(db)
    location = _make_location(db, account.id)
    create_tracked_query(account.id, _payload("Best dentist", location_id=location.id), db)
    brand_level = create_tracked_query(account.id, _payload("Best dentist"), db)

    with pytest.raises(TrackedQueryDuplicateError):
        patch_tracked_query(brand_level, TrackedQueryPatch(location_id=location.id), db)


# --- Cross-client denial -------------------------------------------------


def test_get_tracked_query_is_client_scoped(db):
    from app.services.tracked_query_service import create_tracked_query, get_tracked_query

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    created = create_tracked_query(account_a.id, _payload(), db)

    assert get_tracked_query(account_a.id, created.id, db) is not None
    assert get_tracked_query(account_b.id, created.id, db) is None


def test_list_tracked_queries_is_client_scoped(db):
    from app.services.tracked_query_service import create_tracked_query, list_tracked_queries

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    create_tracked_query(account_a.id, _payload("Query A"), db)
    create_tracked_query(account_b.id, _payload("Query B"), db)

    result = list_tracked_queries(account_a.id, db)
    assert len(result) == 1
    assert result[0].text == "Query A"


# --- Location ownership ---------------------------------------------------


def test_create_rejects_a_location_belonging_to_another_client(db):
    from app.services.tracked_query_service import create_tracked_query, TrackedQueryLocationNotFound

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    with pytest.raises(TrackedQueryLocationNotFound):
        create_tracked_query(account_a.id, _payload(location_id=foreign_location.id), db)


def test_patch_rejects_reassigning_to_a_location_belonging_to_another_client(db):
    from app.services.tracked_query_service import create_tracked_query, patch_tracked_query, TrackedQueryLocationNotFound
    from app.schemas.tracked_query import TrackedQueryPatch

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)
    tracked_query = create_tracked_query(account_a.id, _payload(), db)

    with pytest.raises(TrackedQueryLocationNotFound):
        patch_tracked_query(tracked_query, TrackedQueryPatch(location_id=foreign_location.id), db)


def test_list_rejects_a_location_filter_belonging_to_another_client(db):
    from app.services.tracked_query_service import list_tracked_queries, TrackedQueryLocationNotFound

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    with pytest.raises(TrackedQueryLocationNotFound):
        list_tracked_queries(account_a.id, db, location_id=foreign_location.id)


# --- Archive instead of hard delete ---------------------------------------


def test_archive_deactivates_and_is_excluded_from_default_listing(db):
    from app.services.tracked_query_service import (
        archive_tracked_query,
        create_tracked_query,
        list_tracked_queries,
    )

    account = _make_client(db)
    tracked_query = create_tracked_query(account.id, _payload(), db)

    archived = archive_tracked_query(tracked_query, db)

    assert archived.is_active is False
    assert list_tracked_queries(account.id, db) == []
    assert list_tracked_queries(account.id, db, active=False) == [archived]


def test_archive_does_not_delete_the_row(db):
    from app.models.tracked_query import TrackedQuery
    from app.services.tracked_query_service import archive_tracked_query, create_tracked_query

    account = _make_client(db)
    tracked_query = create_tracked_query(account.id, _payload(), db)
    archive_tracked_query(tracked_query, db)

    assert db.get(TrackedQuery, tracked_query.id) is not None


# --- Stable ordering --------------------------------------------------------


def test_list_orders_by_priority_score_desc_then_created_at(db):
    from app.services.tracked_query_service import create_tracked_query, list_tracked_queries

    account = _make_client(db)
    low = create_tracked_query(account.id, _payload("Low demand", demand_weight=0.1), db)
    high = create_tracked_query(account.id, _payload("High demand", demand_weight=0.9), db)
    mid = create_tracked_query(account.id, _payload("Mid demand", demand_weight=0.5), db)

    result = list_tracked_queries(account.id, db)

    assert [tq.id for tq in result] == [high.id, mid.id, low.id]


def test_list_breaks_priority_ties_by_created_at(db):
    from app.services.tracked_query_service import create_tracked_query, list_tracked_queries

    account = _make_client(db)
    first = create_tracked_query(account.id, _payload("First query", demand_weight=0.5), db)
    time.sleep(0.01)  # guarantee created_at differs regardless of clock resolution
    second = create_tracked_query(account.id, _payload("Second query", demand_weight=0.5), db)

    result = list_tracked_queries(account.id, db)

    assert [tq.id for tq in result] == [first.id, second.id]


# --- Priority scoring contract ----------------------------------------------


def test_priority_score_matches_the_weighted_contract(db):
    from app.services.tracked_query_service import create_tracked_query

    account = _make_client(db)
    tracked_query = create_tracked_query(
        account.id,
        _payload(
            demand_weight=0.8,
            buyer_stage="decision",
            risk_level="critical",
            recent_change_weight=0.6,
            business_value_weight=0.4,
        ),
        db,
    )

    # demand(0.8*0.35) + buyer_stage(1.0*0.20) + risk(1.0*0.20)
    # + recent_change(0.6*0.15) + business_value(0.4*0.10) = 0.77 -> 77.0
    expected = round(
        (0.8 * 0.35 + 1.0 * 0.20 + 1.0 * 0.20 + 0.6 * 0.15 + 0.4 * 0.10) * 100, 2
    )
    assert tracked_query.priority_score == expected


def test_priority_score_uses_neutral_default_for_omitted_scoring_inputs(db):
    from app.services.tracked_query_service import create_tracked_query

    account = _make_client(db)
    tracked_query = create_tracked_query(
        account.id,
        _payload(demand_weight=0.5, buyer_stage=None, risk_level="standard"),
        db,
    )

    # All five components neutral (0.5) -> 50.0
    assert tracked_query.priority_score == 50.0


def test_priority_score_is_never_client_suppliable(db):
    """The API/service accept business inputs only — priority_score itself
    is not a field on TrackedQueryCreate, so it cannot be set directly."""
    from app.schemas.tracked_query import TrackedQueryCreate

    with pytest.raises(Exception):
        TrackedQueryCreate(text="x", source="manual", intent="brand", priority_score=999)


def test_patch_recomputes_priority_score_when_demand_weight_changes(db):
    from app.services.tracked_query_service import create_tracked_query, patch_tracked_query
    from app.schemas.tracked_query import TrackedQueryPatch

    account = _make_client(db)
    tracked_query = create_tracked_query(account.id, _payload(demand_weight=0.2), db)
    original_score = tracked_query.priority_score

    updated = patch_tracked_query(tracked_query, TrackedQueryPatch(demand_weight=0.9), db)

    assert updated.priority_score != original_score


def test_priority_reasons_flags_notable_drivers(db):
    from app.services.tracked_query_service import create_tracked_query, priority_reasons_for

    account = _make_client(db)
    strong = create_tracked_query(
        account.id,
        _payload("Strong query", demand_weight=0.9, buyer_stage="decision", risk_level="critical"),
        db,
    )
    weak = create_tracked_query(
        account.id,
        _payload("Weak query", demand_weight=0.1, buyer_stage="awareness", risk_level="low"),
        db,
    )

    assert priority_reasons_for(strong) != []
    assert priority_reasons_for(weak) == []


def test_priority_reasons_are_not_persisted_on_the_model(db):
    from app.services.tracked_query_service import create_tracked_query

    account = _make_client(db)
    tracked_query = create_tracked_query(account.id, _payload(), db)

    assert not hasattr(tracked_query, "priority_reasons")
