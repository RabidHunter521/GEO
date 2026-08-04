"""Persistence and schema contract for a client's industry intelligence pack.

Phase 4 stores only the pack selection on Client; pack-specific business data
stays in the shared Truth Vault. These tests pin three things that have each
cost this codebase real bugs before:

1. A field on the model but absent from the Pydantic schemas is silently
   dropped (`Client.phone` shipped that way and made a headline feature
   permanently unreachable).
2. `industry_pack_version` is code-versioned, so it must not be admin-settable.
3. Changing an already-chosen pack invalidates generated queries and benchmark
   comparability, so it may not happen without explicit confirmation.
"""
import uuid

import pytest
from pydantic import ValidationError

from app.core.constants import INDUSTRY_PACK_KEYS
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate


def _client(**overrides) -> Client:
    fields = {
        "id": uuid.uuid4(),
        "name": "Pack Co",
        "website": "https://pack.example",
        "industry": "Dental Clinic",
    }
    fields.update(overrides)
    return Client(**fields)


def test_supported_pack_keys_are_exactly_the_three_phase_four_packs():
    # The registry (Task 2) asserts its own keys against this constant, so a
    # pack added in code without updating this tuple fails a test rather than
    # silently becoming unselectable.
    assert INDUSTRY_PACK_KEYS == ("healthcare", "fnb", "local_services")


def test_existing_clients_have_null_pack_fields(db):
    """Pre-migration clients must remain valid with no pack chosen."""
    row = _client()
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.industry_pack is None
    assert row.industry_subcategory is None
    assert row.industry_pack_version is None


def test_pack_fields_persist(db):
    row = _client(
        industry_pack="healthcare",
        industry_subcategory="dental",
        industry_pack_version="1.0.0",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.industry_pack == "healthcare"
    assert row.industry_subcategory == "dental"
    assert row.industry_pack_version == "1.0.0"


def test_prospect_creation_needs_no_pack(db):
    """A prospect is scanned for cold outreach before anyone reviews its pack."""
    payload = ClientCreate(name="Lead Co", website="https://lead.example", industry="Cafe")
    assert payload.is_prospect is False

    row = _client(name=payload.name, website=payload.website,
                  industry=payload.industry, is_prospect=True)
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.is_prospect is True
    assert row.industry_pack is None


@pytest.mark.parametrize("key", ["healthcare", "fnb", "local_services"])
def test_update_schema_accepts_every_supported_pack(key):
    assert ClientUpdate(industry_pack=key).industry_pack == key


@pytest.mark.parametrize("key", ["retail", "HEALTHCARE", "health care", "", "healthcare "])
def test_update_schema_rejects_unsupported_pack_key(key):
    with pytest.raises(ValidationError):
        ClientUpdate(industry_pack=key)


def test_update_schema_allows_clearing_the_pack():
    """None is "no pack reviewed yet", which must stay reachable."""
    assert ClientUpdate(industry_pack=None).industry_pack is None


def test_pack_version_is_not_admin_settable():
    """Pack definitions are code-versioned; an admin must never type a version.

    Pydantic ignores unknown input by default, so the guarantee is structural:
    the field simply does not exist on the update schema.
    """
    assert "industry_pack_version" not in ClientUpdate.model_fields
    parsed = ClientUpdate(industry_pack_version="9.9.9")
    assert not hasattr(parsed, "industry_pack_version")


def test_pack_fields_are_readable_on_the_response_schema():
    """The `phone` regression in reverse: a stored field absent from the
    response schema is invisible to every admin surface."""
    for field in ("industry_pack", "industry_subcategory", "industry_pack_version"):
        assert field in ClientResponse.model_fields


def test_confirm_pack_change_is_a_control_field_not_a_column():
    """It gates the mutation; it must never be written to the clients row."""
    assert "confirm_pack_change" in ClientUpdate.model_fields
    assert not hasattr(Client, "confirm_pack_change")
    assert ClientUpdate().confirm_pack_change is False


# --- version stamping and subcategory validity (registry-backed) -------------
#
# These exercise the admin route against a REGISTERED pack. The three real packs
# arrive in Tasks 3-5, so a fixture pack is registered for the duration of each
# test; the behaviour under test is the wiring, not the pack's content.

def _registered_pack(monkeypatch, *, version="2.1.0", subcategories=("dental", "specialist")):
    from app.industry_packs import registry
    from app.industry_packs.base import (
        IndustryPack, QueryTemplate, RiskRule, TrustedSourceType, TruthFieldDefinition,
    )

    pack = IndustryPack(
        key="healthcare",
        version=version,
        label="Healthcare",
        subcategories=subcategories,
        truth_fields=(TruthFieldDefinition(
            key="practitioner_name", label="Practitioner name",
            value_type="text", scope="location",
        ),),
        query_templates=(QueryTemplate(
            id="brand_overview", template="What is {brand}?",
            buyer_stage="awareness", commercial_intent="low", location_required=False,
        ),),
        risk_rules=(RiskRule(
            id="credentials", fact_type="practitioner", fact_key="qualification",
            severity="critical",
            review_instruction="Confirm the stated qualification against the approved fact.",
        ),),
        trusted_sources=(TrustedSourceType(key="official_website", label="Official website"),),
    )
    monkeypatch.setitem(registry._PACKS, pack.key, pack)
    return pack


def _patch_client(app, get_db, existing, payload):
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.refresh = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        return TestClient(app).patch(f"/api/v1/clients/{existing.id}", json=payload)
    finally:
        app.dependency_overrides.clear()


def _api_client_row(**overrides):
    from tests.test_api_clients import _fake_client

    row = _fake_client("Pack Co")
    row.enabled_platforms = ["chatgpt", "perplexity", "gemini", "claude"]
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_selecting_a_pack_stamps_the_registry_version(monkeypatch):
    """The version records which pack definition a client is configured against;
    an admin must never type it, so the server stamps it on selection."""
    from tests.test_api_clients import _make_app

    _registered_pack(monkeypatch, version="2.1.0")
    app, get_db = _make_app()
    row = _api_client_row(industry_pack=None, industry_pack_version=None)

    response = _patch_client(app, get_db, row, {"industry_pack": "healthcare"})

    assert response.status_code == 200
    assert row.industry_pack_version == "2.1.0"


def test_switching_packs_restamps_rather_than_clearing(monkeypatch):
    from tests.test_api_clients import _make_app

    _registered_pack(monkeypatch, version="2.1.0")
    app, get_db = _make_app()
    row = _api_client_row(industry_pack="fnb", industry_pack_version="1.0.0")

    response = _patch_client(
        app, get_db, row, {"industry_pack": "healthcare", "confirm_pack_change": True}
    )

    assert response.status_code == 200
    assert row.industry_pack_version == "2.1.0"


def test_unregistered_pack_stamps_null_instead_of_500(monkeypatch):
    """Tasks 3-5 have not landed for every key; the admin API must degrade."""
    from tests.test_api_clients import _make_app

    app, get_db = _make_app()
    row = _api_client_row(industry_pack=None, industry_pack_version=None)

    response = _patch_client(app, get_db, row, {"industry_pack": "local_services"})

    assert response.status_code == 200
    assert row.industry_pack_version is None


def test_subcategory_must_belong_to_the_selected_pack(monkeypatch):
    _registered_pack(monkeypatch, subcategories=("dental", "specialist"))
    from tests.test_api_clients import _make_app

    app, get_db = _make_app()
    row = _api_client_row(industry_pack="healthcare", industry_subcategory="dental")

    response = _patch_client(app, get_db, row, {"industry_subcategory": "cafe"})

    assert response.status_code == 422
    assert "cafe" in response.json()["detail"]


def test_valid_subcategory_is_accepted(monkeypatch):
    _registered_pack(monkeypatch, subcategories=("dental", "specialist"))
    from tests.test_api_clients import _make_app

    app, get_db = _make_app()
    row = _api_client_row(industry_pack="healthcare", industry_subcategory="dental")

    response = _patch_client(app, get_db, row, {"industry_subcategory": "specialist"})

    assert response.status_code == 200
    assert row.industry_subcategory == "specialist"


def test_subcategory_is_validated_against_the_merged_pack(monkeypatch):
    """Sending a new pack and a subcategory from the OLD pack in one request
    must fail — the check runs on merged state, not on the request alone."""
    _registered_pack(monkeypatch, subcategories=("dental", "specialist"))
    from tests.test_api_clients import _make_app

    app, get_db = _make_app()
    row = _api_client_row(industry_pack="fnb", industry_subcategory="cafe")

    response = _patch_client(
        app, get_db, row,
        {"industry_pack": "healthcare", "industry_subcategory": "cafe",
         "confirm_pack_change": True},
    )

    assert response.status_code == 422


def test_subcategory_is_not_rejected_when_the_pack_is_unregistered(monkeypatch):
    """An empty subcategory list means "cannot validate", not "reject all"."""
    from tests.test_api_clients import _make_app

    app, get_db = _make_app()
    row = _api_client_row(industry_pack="local_services", industry_subcategory=None)

    response = _patch_client(app, get_db, row, {"industry_subcategory": "plumbing"})

    assert response.status_code == 200
    assert row.industry_subcategory == "plumbing"
