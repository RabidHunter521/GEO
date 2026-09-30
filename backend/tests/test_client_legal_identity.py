"""Client legal identity (legal_name + SSM registration_number): admin-only,
stamped into schema.json deterministically, never used in scans or the view."""
import json
import uuid

from app.models.client import Client
from app.services.toolkit_service import apply_legal_identity

GRAPH = json.dumps({
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "Dentist", "name": "Acme Dental"},
        {"@type": "Organization", "name": "Acme Dental"},
        {"@type": "WebSite", "url": "https://acme.my"},
        {"@type": "FAQPage", "mainEntity": []},
    ],
})


def _client(**kw) -> Client:
    return Client(id=uuid.uuid4(), name="Acme Dental", website="https://acme.my", industry="Dental", **kw)


def test_no_identity_leaves_schema_untouched():
    assert apply_legal_identity(GRAPH, _client()) == GRAPH


def test_identity_stamped_on_business_nodes_only():
    out = json.loads(apply_legal_identity(
        GRAPH, _client(legal_name="Acme Dental Sdn. Bhd.", registration_number="202301012345")
    ))
    business, org, site, faq = out["@graph"]
    for node in (business, org):
        assert node["legalName"] == "Acme Dental Sdn. Bhd."
        assert node["identifier"]["propertyID"] == "SSM"
        assert node["identifier"]["value"] == "202301012345"
    assert "legalName" not in site and "identifier" not in site
    assert "legalName" not in faq


def test_only_the_fields_that_are_set():
    out = json.loads(apply_legal_identity(GRAPH, _client(legal_name="Acme Dental Sdn. Bhd.")))
    assert out["@graph"][0]["legalName"] == "Acme Dental Sdn. Bhd."
    assert "identifier" not in out["@graph"][0]


def test_single_object_without_graph():
    doc = json.dumps({"@context": "https://schema.org", "@type": "LocalBusiness", "name": "X"})
    out = json.loads(apply_legal_identity(doc, _client(registration_number="202301012345")))
    assert out["identifier"]["value"] == "202301012345"


def test_not_in_client_view_schemas():
    from app.schemas import client_view

    for name in dir(client_view):
        fields = getattr(getattr(client_view, name), "model_fields", None)
        if isinstance(fields, dict):
            assert "legal_name" not in fields, name
            assert "registration_number" not in fields, name


def test_not_used_by_scan_query_builders():
    from pathlib import Path

    services = Path(__file__).resolve().parent.parent / "app" / "services"
    for f in ("query_builder.py", "pack_query_service.py", "query_sampling_service.py"):
        src = (services / f).read_text()
        assert "legal_name" not in src and "registration_number" not in src, f


def test_update_validates_registration_number():
    import pytest
    from pydantic import ValidationError
    from app.schemas.client import ClientUpdate

    assert ClientUpdate(registration_number="202301012345 (1501234-X)").registration_number
    with pytest.raises(ValidationError):
        ClientUpdate(registration_number="<script>")
