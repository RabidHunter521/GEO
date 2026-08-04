"""Service-level invariants for the conversion-event evidence ledger:
idempotent import, evidence-level constraints, currency allowlist, the
negative-value-only-for-estimated rule, cross-client isolation, and
per-currency, per-evidence-level summary aggregation.
"""

from datetime import date, datetime, timezone

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


def _event(
    event_type="lead",
    source="manual",
    evidence_level="observed",
    external_event_id="ext-1",
    occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    value_minor=1000,
    currency="MYR",
    **overrides,
):
    from app.schemas.conversion_event import ConversionEventCreate

    body = dict(
        event_type=event_type,
        source=source,
        evidence_level=evidence_level,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        value_minor=value_minor,
        currency=currency,
    )
    body.update(overrides)
    return ConversionEventCreate(**body)


# --- Idempotent import -----------------------------------------------------


def test_import_inserts_new_events(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    result = conversion_evidence_service.import_events(
        account.id, [_event(), _event(external_event_id="ext-2")], db
    )
    assert result.inserted == 2
    assert result.updated == 0
    assert result.total == 2


def test_reimporting_the_same_external_id_updates_instead_of_duplicating(db):
    from app.services import conversion_evidence_service
    from app.models.conversion_event import ConversionEvent

    account = _make_client(db)
    conversion_evidence_service.import_events(account.id, [_event(value_minor=1000)], db)
    result = conversion_evidence_service.import_events(
        account.id, [_event(value_minor=2500)], db
    )

    assert result.inserted == 0
    assert result.updated == 1
    rows = db.query(ConversionEvent).filter(ConversionEvent.client_id == account.id).all()
    assert len(rows) == 1
    assert rows[0].value_minor == 2500


def test_manual_entries_without_external_id_always_insert_fresh(db):
    from app.services import conversion_evidence_service
    from app.models.conversion_event import ConversionEvent

    account = _make_client(db)
    payload = _event(source="manual", external_event_id=None, occurred_at=None, evidence_level="estimated")
    conversion_evidence_service.import_events(account.id, [payload], db)
    conversion_evidence_service.import_events(account.id, [payload], db)

    rows = db.query(ConversionEvent).filter(ConversionEvent.client_id == account.id).all()
    assert len(rows) == 2


def test_import_scopes_dedup_to_client_and_source(db):
    """Same external_event_id under a different client (or source) is not a collision."""
    from app.services import conversion_evidence_service
    from app.models.conversion_event import ConversionEvent

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    conversion_evidence_service.import_events(account_a.id, [_event(external_event_id="shared")], db)
    conversion_evidence_service.import_events(account_b.id, [_event(external_event_id="shared")], db)

    rows = db.query(ConversionEvent).all()
    assert len(rows) == 2


# --- Evidence level validation ----------------------------------------------


def test_observed_requires_external_event_id(db):
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventValidationError

    account = _make_client(db)
    payload = _event(evidence_level="observed", external_event_id=None)
    with pytest.raises(ConversionEventValidationError):
        conversion_evidence_service.import_events(account.id, [payload], db)


def test_observed_requires_occurred_at(db):
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventValidationError

    account = _make_client(db)
    payload = _event(evidence_level="observed", occurred_at=None)
    with pytest.raises(ConversionEventValidationError):
        conversion_evidence_service.import_events(account.id, [payload], db)


def test_estimated_does_not_require_external_id_or_occurred_at(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    payload = _event(
        evidence_level="estimated",
        external_event_id=None,
        occurred_at=None,
        calculation_method="linear_projection",
        calculation_version="v1",
    )
    result = conversion_evidence_service.import_events(account.id, [payload], db)
    assert result.inserted == 1


def test_invalid_event_in_batch_aborts_the_whole_import(db):
    """A batch validates atomically — no partial writes on a bad row."""
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventValidationError
    from app.models.conversion_event import ConversionEvent

    account = _make_client(db)
    good = _event(external_event_id="good-1")
    bad = _event(external_event_id=None, evidence_level="observed")

    with pytest.raises(ConversionEventValidationError):
        conversion_evidence_service.import_events(account.id, [good, bad], db)

    rows = db.query(ConversionEvent).filter(ConversionEvent.client_id == account.id).all()
    assert rows == []


# --- Currency allowlist ------------------------------------------------------


def test_unsupported_currency_is_rejected(db):
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventValidationError

    account = _make_client(db)
    payload = _event(currency="XYZ")
    with pytest.raises(ConversionEventValidationError):
        conversion_evidence_service.import_events(account.id, [payload], db)


@pytest.mark.parametrize("currency", ["MYR", "USD", "SGD", "GBP", "EUR", "AUD"])
def test_allowed_currencies_are_accepted(db, currency):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    payload = _event(currency=currency, external_event_id=f"ext-{currency}")
    result = conversion_evidence_service.import_events(account.id, [payload], db)
    assert result.inserted == 1


# --- Negative value constraint ----------------------------------------------


def test_negative_value_rejected_for_non_estimated_evidence(db):
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventValidationError

    account = _make_client(db)
    payload = _event(evidence_level="observed", value_minor=-500)
    with pytest.raises(ConversionEventValidationError):
        conversion_evidence_service.import_events(account.id, [payload], db)


def test_negative_value_allowed_for_estimated_evidence(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    payload = _event(
        evidence_level="estimated",
        external_event_id=None,
        occurred_at=None,
        value_minor=-500,
        calculation_method="refund_adjustment",
        calculation_version="v1",
    )
    result = conversion_evidence_service.import_events(account.id, [payload], db)
    assert result.inserted == 1


# --- Location ownership -----------------------------------------------------


def test_import_rejects_a_location_from_another_client(db):
    from app.services import conversion_evidence_service
    from app.services.conversion_evidence_service import ConversionEventLocationNotFound

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    foreign_location = _make_location(db, account_b.id)

    payload = _event(location_id=foreign_location.id)
    with pytest.raises(ConversionEventLocationNotFound):
        conversion_evidence_service.import_events(account_a.id, [payload], db)


# --- Listing -----------------------------------------------------------------


def test_list_events_filters_by_evidence_level_and_type(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    conversion_evidence_service.import_events(
        account.id,
        [
            _event(event_type="lead", evidence_level="observed", external_event_id="ext-1"),
            _event(
                event_type="booking",
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                calculation_method="m",
                calculation_version="v1",
            ),
        ],
        db,
    )

    observed_only = conversion_evidence_service.list_events(
        account.id, db, evidence_level="observed"
    )
    assert len(observed_only) == 1
    assert observed_only[0].event_type == "lead"

    booking_only = conversion_evidence_service.list_events(account.id, db, event_type="booking")
    assert len(booking_only) == 1
    assert booking_only[0].evidence_level == "estimated"


def test_list_events_does_not_leak_another_clients_rows(db):
    from app.services import conversion_evidence_service

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    conversion_evidence_service.import_events(account_a.id, [_event(external_event_id="a")], db)
    conversion_evidence_service.import_events(account_b.id, [_event(external_event_id="b")], db)

    rows = conversion_evidence_service.list_events(account_a.id, db)
    assert len(rows) == 1
    assert rows[0].external_event_id == "a"


def test_list_events_respects_date_window(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    conversion_evidence_service.import_events(
        account.id,
        [
            _event(external_event_id="jan", occurred_at=datetime(2026, 1, 15, tzinfo=timezone.utc)),
            _event(external_event_id="jul", occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc)),
        ],
        db,
    )

    rows = conversion_evidence_service.list_events(
        account.id, db, date_from=date(2026, 6, 1), date_to=date(2026, 8, 1)
    )
    assert [row.external_event_id for row in rows] == ["jul"]


# --- Summary aggregation -----------------------------------------------------


def test_summary_never_sums_across_evidence_levels(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    conversion_evidence_service.import_events(
        account.id,
        [
            _event(evidence_level="observed", external_event_id="o1", value_minor=1000),
            _event(evidence_level="attributed", external_event_id="a1", value_minor=500),
            _event(evidence_level="assisted", external_event_id="s1", value_minor=300),
            _event(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=200,
                calculation_method="m",
                calculation_version="v1",
            ),
        ],
        db,
    )

    summaries = conversion_evidence_service.summarize_events(account.id, db)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.observed_value_minor == 1000
    assert summary.attributed_value_minor == 500
    assert summary.assisted_value_minor == 300
    assert summary.estimated_value_minor == 200
    assert summary.event_count_by_level == {
        "observed": 1,
        "attributed": 1,
        "assisted": 1,
        "estimated": 1,
    }


def test_summary_returns_separate_objects_per_currency(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    conversion_evidence_service.import_events(
        account.id,
        [
            _event(currency="MYR", external_event_id="myr-1", value_minor=1000),
            _event(currency="USD", external_event_id="usd-1", value_minor=250),
        ],
        db,
    )

    summaries = conversion_evidence_service.summarize_events(account.id, db)
    by_currency = {summary.currency: summary for summary in summaries}
    assert set(by_currency) == {"MYR", "USD"}
    assert by_currency["MYR"].observed_value_minor == 1000
    assert by_currency["USD"].observed_value_minor == 250


def test_summary_scoped_to_client(db):
    from app.services import conversion_evidence_service

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    conversion_evidence_service.import_events(
        account_a.id, [_event(external_event_id="a", value_minor=1000)], db
    )
    conversion_evidence_service.import_events(
        account_b.id, [_event(external_event_id="b", value_minor=9999)], db
    )

    summaries = conversion_evidence_service.summarize_events(account_a.id, db)
    assert summaries[0].observed_value_minor == 1000


def test_summary_with_no_events_returns_empty_list(db):
    from app.services import conversion_evidence_service

    account = _make_client(db)
    summaries = conversion_evidence_service.summarize_events(account.id, db)
    assert summaries == []
