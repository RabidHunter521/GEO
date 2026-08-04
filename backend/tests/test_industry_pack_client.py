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
