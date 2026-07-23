"""Brand Authority assessment consumes the authority-asset evidence (spec §7)."""


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_prompt_includes_authority_evidence_when_present():
    from app.models.client import Client
    from app.prompts.assessment import build_assessment_prompt
    client = Client(name="Acme Dental", website="https://acme.com",
                    industry="Dental clinic", contact_email="x@acme.com")
    authority = {
        "total": 3, "live": 1, "verified": 1, "missing": 1,
        "verified_names": ["Google Business Profile"], "live_names": ["LinkedIn company page"],
        "missing_names": ["Crunchbase"],
    }
    prompt = build_assessment_prompt(client, "brand_authority", authority=authority)
    assert "Google Business Profile" in prompt
    assert "verified" in prompt.lower()


def test_prompt_omits_block_when_no_authority():
    from app.models.client import Client
    from app.prompts.assessment import build_assessment_prompt
    client = Client(name="Acme Dental", website="https://acme.com",
                    industry="Dental clinic", contact_email="x@acme.com")
    prompt = build_assessment_prompt(client, "brand_authority", authority=None)
    assert "SeenBy-tracked authority assets" not in prompt


def test_version_bumped_to_v3():
    from app.prompts.assessment import BRAND_AUTHORITY_VERSION
    assert BRAND_AUTHORITY_VERSION == "v3"


def test_generate_assessment_passes_authority(db):
    """brand_authority assessment pulls the authority summary and it reaches the prompt."""
    from unittest.mock import MagicMock, patch
    from app.services import assessment_service, authority_service
    client = _make_client(db)
    (gbp,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(gbp, {"status": "verified"}, db)

    captured = {}

    def fake_build(cl, dim, crawl=None, authority=None):
        captured["authority"] = authority
        return "PROMPT"

    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(text='{"score": 60, "bullets": ["ok"], "narrative": "n"}')]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    with patch.object(assessment_service, "build_assessment_prompt", side_effect=fake_build), \
         patch.object(assessment_service, "anthropic_client", return_value=ac), \
         patch.object(assessment_service, "record_llm_call"):
        assessment_service.generate_assessment(client, "brand_authority", db)
    assert captured["authority"] is not None
    assert captured["authority"]["verified"] == 1
