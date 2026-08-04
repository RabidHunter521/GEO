"""What may and may not cross into a content prompt from the Truth Vault.

A content prompt's output becomes client-facing copy. Anything reaching the
model can come back out, so this is a firewall test, not a formatting test: the
model may see approved values and the rules that follow from them, and nothing
else — no drafts, no reviewer notes, no raw conflicts, no internal identifiers.
"""
import uuid

import pytest

from app.industry_packs.fnb import FNB_PACK
from app.industry_packs.healthcare import HEALTHCARE_PACK
from app.industry_packs.local_services import LOCAL_SERVICES_PACK
from app.prompts.industry_pack import build_pack_context
from app.services.pack_query_service import ApprovedFact


class _Client:
    def __init__(self, subcategory="dental"):
        self.id = uuid.uuid4()
        self.name = "Klinik Sihat"
        self.industry = "Dental Clinic"
        self.industry_pack = "healthcare"
        self.industry_subcategory = subcategory
        self.city = "Kuala Lumpur"
        self.state = "Selangor"
        self.country = "Malaysia"
        self.description = "A dental clinic."
        self.target_audience = "Families"


def _facts():
    return [
        ApprovedFact("treatment", "offered", ["braces", "implants"]),
        ApprovedFact("practitioner", "qualification", "BDS"),
        ApprovedFact("payment", "instalment_available", True),
    ]


# --- what must appear -------------------------------------------------------

def test_pack_label_and_subcategory_appear():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    assert "Healthcare" in text
    assert "Dental" in text


def test_approved_fact_values_appear_under_their_pack_labels():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    assert "Treatments offered: braces, implants" in text
    assert "Qualification: BDS" in text


def test_booleans_read_as_words_not_python_literals():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    assert "Instalment plans available: yes" in text
    assert "True" not in text


def test_sensitive_claim_rules_appear():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    assert "do NOT state anything about" in text
    assert "qualification" in text.lower()


def test_the_do_not_invent_rule_is_always_present():
    for pack in (HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK):
        text = build_pack_context(_Client(subcategory=None), pack, [])
        assert "Do not invent facts" in text


# --- what must NOT appear ---------------------------------------------------

def test_internal_identifiers_never_reach_the_model():
    client = _Client()
    text = build_pack_context(client, HEALTHCARE_PACK, _facts())
    assert str(client.id) not in text
    assert "uuid" not in text.lower()
    assert "_id" not in text


def test_unknown_fact_keys_are_dropped_rather_than_shown_raw():
    """A fact the pack does not declare has no label, so it would surface an
    internal key as if it were business vocabulary."""
    facts = _facts() + [ApprovedFact("internal", "scratch_note", "do not print me")]
    text = build_pack_context(_Client(), HEALTHCARE_PACK, facts)
    assert "scratch_note" not in text
    assert "do not print me" not in text


def test_review_instructions_are_not_leaked_into_the_prompt():
    """Risk-rule instructions are written for a human deciding what to CHECK. A
    model given "confirm the stated qualification" tends to claim it did."""
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    for rule in HEALTHCARE_PACK.risk_rules:
        assert rule.review_instruction not in text


def test_no_professional_approval_language():
    """The prompt must not let a model imply regulatory endorsement."""
    for pack in (HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK):
        text = build_pack_context(_Client(), pack, _facts()).lower()
        # the block INSTRUCTS against these; it must never assert them
        assert "is certified by" not in text
        assert "is licensed by" not in text
        assert "is accredited by" not in text


def test_the_context_forbids_implying_endorsement():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts())
    assert "Never imply that this business has been endorsed" in text


@pytest.mark.parametrize("banned", ["citation", "cited", "ranking position", "visibility gap"])
def test_no_banned_client_vocabulary(banned):
    text = build_pack_context(_Client(), HEALTHCARE_PACK, _facts()).lower()
    assert banned not in text


# --- the no-pack path -------------------------------------------------------

def test_an_unpacked_client_gets_an_empty_block():
    """Prompts concatenate this; an unpacked client must produce byte-identical
    output to before Phase 4 existed."""
    assert build_pack_context(_Client(), None, _facts()) == ""


def test_a_packed_client_with_no_approved_facts_still_gets_the_rules():
    text = build_pack_context(_Client(), HEALTHCARE_PACK, [])
    assert "Healthcare" in text
    assert "Do not invent facts" in text
    assert "Verified business facts" not in text


def test_blank_values_do_not_render_empty_lines():
    facts = [ApprovedFact("treatment", "offered", ["", "  "])]
    text = build_pack_context(_Client(), HEALTHCARE_PACK, facts)
    assert "Treatments offered:" not in text


# --- the prompts that consume it -------------------------------------------

def test_content_prompts_carry_the_pack_context():
    from app.prompts.content_analysis import build_suggested_content

    client = _Client()
    with_pack = build_suggested_content(
        client, ["teeth whitening"], pack=HEALTHCARE_PACK, facts=_facts()
    )
    without = build_suggested_content(client, ["teeth whitening"])

    assert "Qualification: BDS" in with_pack
    assert "Qualification: BDS" not in without
    # the unpacked prompt is unchanged from its pre-Phase-4 form
    assert "Do not invent facts" not in without


def test_content_brief_prompt_carries_the_pack_context():
    from app.prompts.content_brief import build_content_brief

    class _Result:
        query_text = "best dentist in KL"
        platform = "chatgpt"

    client = _Client()
    text = build_content_brief(
        client, _Result(), ["Rival Dental"], pack=HEALTHCARE_PACK, facts=_facts()
    )
    assert "Treatments offered: braces, implants" in text
    assert "Do not invent facts" in text


# --- report language --------------------------------------------------------

def test_every_pack_declares_its_own_report_wording():
    """Report text must be pack CONFIGURATION, not `if industry` branches."""
    from app.industry_packs import registry

    for pack in registry.all_packs():
        assert pack.report_fact_label.strip()
        assert "reviewed" in pack.report_fact_label.lower()


def test_pack_report_labels_are_distinct_and_industry_specific():
    from app.industry_packs.fnb import FNB_PACK
    from app.industry_packs.local_services import LOCAL_SERVICES_PACK

    labels = {
        HEALTHCARE_PACK.report_fact_label,
        FNB_PACK.report_fact_label,
        LOCAL_SERVICES_PACK.report_fact_label,
    }
    assert len(labels) == 3
    assert "Practitioner" in HEALTHCARE_PACK.report_fact_label
    assert "Outlet" in FNB_PACK.report_fact_label
    assert "Service-area" in LOCAL_SERVICES_PACK.report_fact_label


def test_report_labels_carry_no_banned_client_vocabulary():
    from app.industry_packs import registry
    from app.services.language_sanitizer import sanitize_text

    for pack in registry.all_packs():
        assert sanitize_text(pack.report_fact_label) == pack.report_fact_label


def test_report_renders_the_pack_label_only_for_packed_clients():
    from app.services.report_service import MisinformationSummary, _build_misinformation_html

    class _Data:
        misinformation = MisinformationSummary(
            open_count=0, fixed_count=0, severity_counts={}, fixed_stories=[],
        )
        pack_fact_label = "Practitioner and treatment facts reviewed"

    packed = _build_misinformation_html(_Data())
    assert "Practitioner and treatment facts reviewed" in packed

    _Data.pack_fact_label = ""
    unpacked = _build_misinformation_html(_Data())
    assert "reviewed" not in unpacked
