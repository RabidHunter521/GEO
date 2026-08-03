"""Truth Vault lifecycle behavior through the real persistence layer."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql


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


def _make_location(db, client_id, name="Orchard"):
    from app.models.business_location import BusinessLocation

    location = BusinessLocation(
        client_id=client_id,
        name=name,
        slug=name.lower(),
        active=True,
    )
    db.add(location)
    db.commit()
    return location


def _fact_payload(**overrides):
    from app.schemas.truth_fact import TruthFactCreate

    values = {"fact_type": "business", "fact_key": "phone"}
    values.update(overrides)
    return TruthFactCreate(**values)


def _version_payload(value, effective_at):
    from app.schemas.truth_fact import TruthFactVersionDraft

    return TruthFactVersionDraft(
        value={"value": value, "display_value": value},
        source_url="https://acme.example/contact",
        effective_from=effective_at,
    )


def test_approving_a_replacement_closes_history_and_excludes_drafts(db):
    from app.services.truth_vault_service import (
        approve_version,
        create_fact,
        current_facts,
        draft_version,
        facts_effective_at,
    )

    client = _make_client(db)
    first_effective_at = datetime(2026, 1, 1, 9, 0, 0)
    replacement_effective_at = datetime(2026, 2, 1, 9, 0, 0)
    fact = create_fact(client.id, _fact_payload(), db)
    first = draft_version(fact, _version_payload("+65 1111 1111", first_effective_at), db)
    approve_version(fact.id, first.id, "reviewer@example.com", db)
    replacement = draft_version(
        fact, _version_payload("+65 2222 2222", replacement_effective_at), db
    )
    approve_version(fact.id, replacement.id, "reviewer@example.com", db)
    pending = draft_version(
        fact, _version_payload("+65 3333 3333", datetime(2026, 3, 1, 9, 0, 0)), db
    )

    db.refresh(first)
    assert first.effective_to == replacement_effective_at - timedelta(microseconds=1)
    assert [item.value_json for item in facts_effective_at(client.id, first_effective_at, db)] == [
        {"value": "+65 1111 1111", "display_value": "+65 1111 1111"}
    ]
    assert [item.value_json for item in current_facts(client.id, db)] == [
        {"value": "+65 2222 2222", "display_value": "+65 2222 2222"}
    ]
    assert pending.status == "draft"


def test_approval_locks_the_fact_row_before_transitioning_versions(db):
    from app.services.truth_vault_service import approve_version, create_fact, draft_version

    client = _make_client(db)
    fact = create_fact(client.id, _fact_payload(), db)
    draft = draft_version(fact, _version_payload("+65 1111 1111", datetime(2026, 1, 1)), db)
    statements = []

    def capture_statement(_conn, clauseelement, *_args):
        statements.append(str(clauseelement.compile(dialect=postgresql.dialect())))

    event.listen(db.bind, "before_execute", capture_statement)
    try:
        approve_version(fact.id, draft.id, "reviewer@example.com", db)
    finally:
        event.remove(db.bind, "before_execute", capture_statement)

    assert any("FROM truth_facts" in statement and "FOR UPDATE" in statement for statement in statements)


def test_create_fact_rejects_a_location_owned_by_another_client(db):
    from app.services.truth_vault_service import TruthVaultLocationNotFound, create_fact

    first_client = _make_client(db)
    second_client = _make_client(db, "Bravo Legal")
    other_location = _make_location(db, second_client.id)

    with pytest.raises(TruthVaultLocationNotFound, match="Location not found"):
        create_fact(first_client.id, _fact_payload(location_id=other_location.id), db)


def test_retiring_a_fact_closes_its_open_approved_period(db):
    from app.services.truth_vault_service import (
        approve_version,
        create_fact,
        current_facts,
        draft_version,
        retire_fact,
    )

    client = _make_client(db)
    fact = create_fact(client.id, _fact_payload(), db)
    effective_at = datetime(2026, 1, 1, 9, 0, 0)
    version = draft_version(fact, _version_payload("+65 1111 1111", effective_at), db)
    approve_version(fact.id, version.id, "reviewer@example.com", db)

    retired = retire_fact(fact.id, datetime(2026, 2, 1, 9, 0, 0), db)

    assert retired.effective_to == datetime(2026, 2, 1, 8, 59, 59, 999999)
    assert current_facts(client.id, db) == []


def test_approval_rejects_a_new_version_that_overlaps_the_current_interval(db):
    from app.services.truth_vault_service import (
        TruthVaultValidationError,
        approve_version,
        create_fact,
        draft_version,
    )

    client = _make_client(db)
    fact = create_fact(client.id, _fact_payload(), db)
    effective_at = datetime(2026, 1, 1, 9, 0, 0)
    first = draft_version(fact, _version_payload("+65 1111 1111", effective_at), db)
    approve_version(fact.id, first.id, "reviewer@example.com", db)
    overlapping = draft_version(fact, _version_payload("+65 2222 2222", effective_at), db)

    with pytest.raises(TruthVaultValidationError, match="follow"):
        approve_version(fact.id, overlapping.id, "reviewer@example.com", db)
