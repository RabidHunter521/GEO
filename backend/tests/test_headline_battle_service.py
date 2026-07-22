import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.services.headline_battle_service import select_headline_battle


def _entry(category, query, competitors_seen, outcome, platform="chatgpt", brief=None):
    return SimpleNamespace(
        category=category, query_text=query, competitors_seen=competitors_seen,
        outcome=outcome, platform=platform, brief=brief,
    )


def _wl(entries):
    return SimpleNamespace(entries=entries)


def _call(entries):
    with patch("app.services.headline_battle_service.compute_win_loss", return_value=_wl(entries)):
        return select_headline_battle(uuid.uuid4(), db=object())


def test_none_when_no_lost_entries():
    entries = [_entry("recommendation", "best clinic KL", [], "won")]
    assert _call(entries) is None


def test_picks_recommendation_over_local():
    entries = [
        _entry("local", "best dentist near me", ["RivalCo"], "lost"),
        _entry("recommendation", "best invisalign KL", ["RivalCo"], "lost"),
    ]
    b = _call(entries)
    assert b is not None
    assert b.query_text == "best invisalign KL"  # recommendation ranks first


def test_names_primary_threat_competitor():
    # RivalCo appears in 2 lost battles, OtherCo in 1 -> RivalCo is the primary threat.
    entries = [
        _entry("recommendation", "q1", ["OtherCo"], "lost"),
        _entry("recommendation", "q2", ["RivalCo"], "lost"),
        _entry("local", "q3", ["RivalCo"], "lost"),
    ]
    b = _call(entries)
    # primary-threat-present battles rank ahead; among recommendation, q2 has RivalCo.
    assert b.rival_name == "RivalCo"
    assert b.query_text == "q2"


def test_reuses_existing_brief_as_move():
    brief = SimpleNamespace(title="Win Invisalign in KL", angle="Cover pricing and clinics.")
    entries = [_entry("recommendation", "best invisalign KL", ["RivalCo"], "lost", brief=brief)]
    b = _call(entries)
    assert b.move_title == "Win Invisalign in KL"
    assert b.move_angle == "Cover pricing and clinics."


def test_move_none_when_no_brief():
    entries = [_entry("recommendation", "best invisalign KL", ["RivalCo"], "lost", brief=None)]
    b = _call(entries)
    assert b.move_title is None and b.move_angle is None


def test_platform_label_mapped():
    entries = [_entry("recommendation", "q", ["RivalCo"], "lost", platform="chatgpt")]
    b = _call(entries)
    assert b.platform_label == "ChatGPT"  # mapped via PLATFORM_LABELS, not the raw code
