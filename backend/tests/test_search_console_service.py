"""Service-level invariants for the Search Console signal import layer:
idempotent upsert, in-batch duplicate handling, date/query filtering,
property/tenant scoping, and location ownership.
"""

from datetime import date

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


def _signal(**overrides):
    from app.schemas.search_query_signal import SearchQuerySignalCreate

    body = {
        "property_uri": "sc-domain:example.com",
        "signal_date": date(2026, 8, 1),
        "query": "best dentist in kl",
        "page": "https://example.com/",
        "clicks": 10,
        "impressions": 100,
        "ctr": 0.1,
        "position": 4.5,
    }
    body.update(overrides)
    return SearchQuerySignalCreate(**body)


# --- Upsert idempotency -------------------------------------------------


def test_upsert_inserts_new_signals(db):
    from app.services import search_console_service

    account = _make_client(db)
    result = search_console_service.upsert_signals(account.id, [_signal()], db)

    assert result.inserted == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert result.total == 1


def test_upsert_is_idempotent_on_repeated_sync(db):
    from app.services import search_console_service

    account = _make_client(db)
    signal = _signal()

    first = search_console_service.upsert_signals(account.id, [signal], db)
    second = search_console_service.upsert_signals(account.id, [signal], db)

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.updated == 1

    status = search_console_service.get_sync_status(account.id, db)
    assert status.total_signals == 1


def test_upsert_updates_metrics_on_existing_row(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(account.id, [_signal(clicks=10)], db)
    search_console_service.upsert_signals(account.id, [_signal(clicks=25, impressions=250)], db)

    signals = search_console_service.list_signals(account.id, db)
    assert len(signals) == 1
    assert signals[0].clicks == 25
    assert signals[0].impressions == 250


def test_upsert_treats_different_device_or_country_as_distinct_rows(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(
        account.id, [_signal(device="DESKTOP"), _signal(device="MOBILE")], db
    )

    status = search_console_service.get_sync_status(account.id, db)
    assert status.total_signals == 2


def test_upsert_with_empty_list_is_a_no_op(db):
    from app.services import search_console_service

    account = _make_client(db)
    result = search_console_service.upsert_signals(account.id, [], db)

    assert result == search_console_service.UpsertResult(
        inserted=0, updated=0, skipped=0, total=0
    )


# --- In-batch duplicate handling ----------------------------------------


def test_upsert_skips_duplicate_keys_within_the_same_batch(db):
    from app.services import search_console_service

    account = _make_client(db)
    signal = _signal()
    result = search_console_service.upsert_signals(account.id, [signal, signal], db)

    assert result.inserted == 1
    assert result.skipped == 1
    assert result.total == 2


# --- Date window / query filtering --------------------------------------


def test_list_signals_filters_by_date_window(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(
        account.id,
        [
            _signal(signal_date=date(2026, 7, 1)),
            _signal(signal_date=date(2026, 8, 1)),
            _signal(signal_date=date(2026, 9, 1)),
        ],
        db,
    )

    signals = search_console_service.list_signals(
        account.id, db, date_from=date(2026, 7, 15), date_to=date(2026, 8, 15)
    )
    assert [s.signal_date for s in signals] == [date(2026, 8, 1)]


def test_list_signals_filters_by_query_substring(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(
        account.id,
        [
            _signal(query="best dentist in kl", page="https://example.com/a"),
            _signal(query="emergency dentist kl", page="https://example.com/b"),
            _signal(query="best lawyer in kl", page="https://example.com/c"),
        ],
        db,
    )

    signals = search_console_service.list_signals(account.id, db, query_filter="dentist")
    assert {s.query for s in signals} == {"best dentist in kl", "emergency dentist kl"}


def test_list_signals_paginates_with_limit_and_offset(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(
        account.id,
        [
            _signal(signal_date=date(2026, 8, 1), page="https://example.com/1"),
            _signal(signal_date=date(2026, 8, 2), page="https://example.com/2"),
            _signal(signal_date=date(2026, 8, 3), page="https://example.com/3"),
        ],
        db,
    )

    page_1 = search_console_service.list_signals(account.id, db, limit=2, offset=0)
    page_2 = search_console_service.list_signals(account.id, db, limit=2, offset=2)

    assert len(page_1) == 2
    assert len(page_2) == 1
    # Newest signal_date first.
    assert page_1[0].signal_date == date(2026, 8, 3)


# --- Property / tenant scoping -------------------------------------------


def test_signals_do_not_leak_across_clients(db):
    from app.services import search_console_service

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    search_console_service.upsert_signals(account_a.id, [_signal(query="query a")], db)
    search_console_service.upsert_signals(account_b.id, [_signal(query="query b")], db)

    signals_a = search_console_service.list_signals(account_a.id, db)
    assert [s.query for s in signals_a] == ["query a"]


def test_sync_status_reports_property_uris_and_date_range(db):
    from app.services import search_console_service

    account = _make_client(db)
    search_console_service.upsert_signals(
        account.id,
        [
            _signal(property_uri="sc-domain:example.com", signal_date=date(2026, 7, 1)),
            _signal(property_uri="sc-domain:other.com", signal_date=date(2026, 8, 1)),
        ],
        db,
    )

    status = search_console_service.get_sync_status(account.id, db)
    assert status.property_uris == ["sc-domain:example.com", "sc-domain:other.com"]
    assert status.earliest_signal_date == date(2026, 7, 1)
    assert status.latest_signal_date == date(2026, 8, 1)
    assert status.total_signals == 2
    assert status.last_synced_at is not None


def test_sync_status_for_client_with_no_signals(db):
    from app.services import search_console_service

    account = _make_client(db)
    status = search_console_service.get_sync_status(account.id, db)

    assert status.property_uris == []
    assert status.total_signals == 0
    assert status.earliest_signal_date is None
    assert status.latest_signal_date is None
    assert status.last_synced_at is None


# --- Location ownership ---------------------------------------------------


def test_upsert_rejects_a_location_from_another_client(db):
    from app.services import search_console_service

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    with pytest.raises(search_console_service.SearchConsoleLocationNotFound):
        search_console_service.upsert_signals(
            account_a.id, [_signal(location_id=foreign_location.id)], db
        )


def test_upsert_accepts_a_location_owned_by_the_same_client(db):
    from app.services import search_console_service

    account = _make_client(db)
    location = _make_location(db, account.id)

    result = search_console_service.upsert_signals(
        account.id, [_signal(location_id=location.id)], db
    )
    assert result.inserted == 1

    signals = search_console_service.list_signals(account.id, db)
    assert signals[0].location_id == location.id


def test_upsert_rejects_the_whole_batch_when_any_location_is_invalid(db):
    import uuid

    from app.services import search_console_service

    account = _make_client(db)
    valid_location = _make_location(db, account.id)
    nonexistent_location_id = uuid.uuid4()

    with pytest.raises(search_console_service.SearchConsoleLocationNotFound):
        search_console_service.upsert_signals(
            account.id,
            [
                _signal(location_id=valid_location.id, page="https://example.com/a"),
                _signal(location_id=nonexistent_location_id, page="https://example.com/b"),
            ],
            db,
        )
    # Nothing from the rejected batch should have been committed.
    status = search_console_service.get_sync_status(account.id, db)
    assert status.total_signals == 0
