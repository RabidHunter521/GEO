"""Service-level invariants for the business-impact evidence ladder:
per-currency separation (inherited from conversion_evidence_service),
calculation_version stamping, data-driven caveat generation, and empty-data
handling.
"""

from datetime import date, datetime, timezone


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


def _import(db, client_id, events):
    from app.services import conversion_evidence_service

    return conversion_evidence_service.import_events(client_id, events, db)


# --- Basic aggregation -------------------------------------------------------


def test_impact_summary_wraps_conversion_summary_values(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(
        db,
        account.id,
        [
            _event(evidence_level="observed", external_event_id="o1", value_minor=1000),
            _event(evidence_level="attributed", external_event_id="a1", value_minor=400),
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
    )

    summaries = business_impact_service.get_impact_summary(account.id, db)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.observed_value_minor == 1000
    assert summary.attributed_value_minor == 400
    assert summary.assisted_value_minor == 300
    assert summary.estimated_value_minor == 200
    assert summary.currency == "MYR"
    assert summary.calculation_version == "impact_v1"


def test_impact_summary_never_collapses_evidence_levels(db):
    """No field on ImpactSummary sums across evidence levels — the model
    itself has no such field, so this asserts the shape stays that way."""
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(value_minor=1000)])

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    field_names = set(type(summary).model_fields.keys())
    assert "total_value_minor" not in field_names
    assert "value_minor" not in field_names


# --- Per-currency separation --------------------------------------------------


def test_mixed_currencies_produce_separate_summaries(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(
        db,
        account.id,
        [
            _event(currency="MYR", external_event_id="myr-1", value_minor=1000),
            _event(currency="USD", external_event_id="usd-1", value_minor=250),
        ],
    )

    summaries = business_impact_service.get_impact_summary(account.id, db)
    by_currency = {s.currency: s for s in summaries}
    assert set(by_currency) == {"MYR", "USD"}
    assert by_currency["MYR"].observed_value_minor == 1000
    assert by_currency["USD"].observed_value_minor == 250


def test_scoped_to_client(db):
    from app.services import business_impact_service

    account_a = _make_client(db, "Acme Dental")
    account_b = _make_client(db, "Bravo Legal")
    _import(db, account_a.id, [_event(external_event_id="a", value_minor=1000)])
    _import(db, account_b.id, [_event(external_event_id="b", value_minor=9999)])

    summaries = business_impact_service.get_impact_summary(account_a.id, db)
    assert len(summaries) == 1
    assert summaries[0].observed_value_minor == 1000


# --- Window ------------------------------------------------------------------


def test_window_is_carried_through_to_the_summary(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(value_minor=1000)])

    date_from = date(2026, 1, 1)
    date_to = date(2026, 12, 31)
    summary = business_impact_service.get_impact_summary(
        account.id, db, date_from=date_from, date_to=date_to
    )[0]
    assert summary.window_start == date_from
    assert summary.window_end == date_to


# --- Empty data ----------------------------------------------------------------


def test_empty_data_returns_empty_list(db):
    from app.services import business_impact_service

    account = _make_client(db)
    summaries = business_impact_service.get_impact_summary(account.id, db)
    assert summaries == []


# --- Caveats -------------------------------------------------------------------


def test_never_sum_caveat_always_present(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(value_minor=1000)])

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert (
        "Values are separated by evidence level and must not be summed into a "
        "single total" in summary.caveats
    )


def test_estimated_caveat_appears_only_when_estimated_events_exist(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(evidence_level="observed", value_minor=1000)])

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert not any("modeled projections" in c for c in summary.caveats)

    _import(
        db,
        account.id,
        [
            _event(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=200,
                calculation_method="m",
                calculation_version="v1",
            )
        ],
    )
    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert any("modeled projections" in c for c in summary.caveats)


def test_no_observed_caveat_appears_when_observed_events_absent(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(
        db,
        account.id,
        [
            _event(
                evidence_level="estimated",
                external_event_id=None,
                occurred_at=None,
                value_minor=200,
                calculation_method="m",
                calculation_version="v1",
            )
        ],
    )

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert any("No directly observed" in c for c in summary.caveats)


def test_no_observed_caveat_absent_when_observed_events_exist(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(evidence_level="observed", value_minor=1000)])

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert not any("No directly observed" in c for c in summary.caveats)


def test_attributed_caveat_appears_only_when_attributed_events_exist(db):
    from app.services import business_impact_service

    account = _make_client(db)
    _import(db, account.id, [_event(evidence_level="observed", value_minor=1000)])

    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert not any("configured source rules" in c for c in summary.caveats)

    _import(
        db,
        account.id,
        [_event(evidence_level="attributed", external_event_id="a1", value_minor=400)],
    )
    summary = business_impact_service.get_impact_summary(account.id, db)[0]
    assert any("configured source rules" in c for c in summary.caveats)
