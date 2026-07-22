import uuid
from unittest.mock import patch

from app.core.constants import DIGEST_STATIC_TIPS
from app.models.client import Client
from app.services.claude_action import get_digest_action
from app.services.digest_tip_service import select_digest_tip
from app.services.headline_battle_service import HeadlineBattle


def make_client(**over):
    defaults = dict(
        id=uuid.uuid4(), name="Klinik Aisyah", website="https://ka.my",
        industry="dental clinic", brand_authority_score=60,
        content_quality_score=70, technical_foundations_verified=True,
        structured_data_verified=True,
    )
    defaults.update(over)
    return Client(**defaults)


def battle(move=None):
    return HeadlineBattle(
        rival_name="Dr. Lim Dental", query_text="Best dental clinic in KL",
        platform_label="ChatGPT", category="recommendation",
        move_title=move, move_angle=None,
    )


def test_rung1_battle_tip_names_query_and_rival():
    tip = select_digest_tip(make_client(), battle(), 55.0)
    assert "Best dental clinic in KL" in tip
    assert "Dr. Lim Dental" in tip


def test_rung2_toolkit_tip_when_no_battle_and_llms_unverified():
    c = make_client(technical_foundations_verified=False)
    tip = select_digest_tip(c, None, 55.0)
    assert "llms.txt" in tip


def test_rung2_schema_tip_when_only_structured_data_unverified():
    c = make_client(structured_data_verified=False)
    tip = select_digest_tip(c, None, 55.0)
    assert "structured data" in tip.lower()


def test_rung3_weakest_dimension_when_no_battle_and_toolkit_verified():
    c = make_client(brand_authority_score=10)
    tip = select_digest_tip(c, None, 90.0)
    assert "review" in tip.lower() or "authority" in tip.lower() or "profile" in tip.lower()


def test_rung4_band_fallback_for_brand_new_client():
    # Everything verified, all dimensions equal-ish, no battle: rung 3 still
    # fires (there is always a weakest dimension when a score exists) — the band
    # fallback is reachable only when citability is None-like (no scan basis).
    tip = select_digest_tip(make_client(), None, None)
    assert tip in DIGEST_STATIC_TIPS.values()


def test_get_digest_action_uses_fallback_tip_below_gate():
    c = make_client()
    tip = get_digest_action(c, 50.0, 48.0, fallback_tip="CUSTOM FALLBACK")
    assert tip == "CUSTOM FALLBACK"


def test_get_digest_action_static_floor_without_fallback():
    c = make_client()
    tip = get_digest_action(c, 50.0, 48.0)
    assert tip in DIGEST_STATIC_TIPS.values()


def test_get_digest_action_claude_failure_falls_to_fallback():
    c = make_client()
    with patch("app.services.claude_action._generate_claude_action", side_effect=RuntimeError):
        tip = get_digest_action(c, 50.0, 30.0, fallback_tip="CUSTOM FALLBACK")
    assert tip == "CUSTOM FALLBACK"


def test_no_banned_vocabulary():
    for args in [(make_client(), battle(), 40.0), (make_client(technical_foundations_verified=False), None, 40.0)]:
        tip = select_digest_tip(*args)
        for banned in ("cited", "uncited", "citation rate", "ranking position", "visibility gap"):
            assert banned not in tip.lower()
