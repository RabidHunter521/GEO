# backend/tests/test_cost_tracker.py
from unittest.mock import MagicMock, patch

import pytest

from app.services.cost_tracker import _TOKEN_COST, _compute_cost, record_llm_usage

# The four scan-platform models. P1-4: these were absent from the pricing table,
# so even once logged they computed $0. They must price at a nonzero rate.
SCAN_PLATFORM_MODELS = ["gpt-5-mini", "sonar", "gemini-2.5-flash-lite"]


@pytest.mark.parametrize("model", SCAN_PLATFORM_MODELS)
def test_scan_platform_model_has_nonzero_pricing(model):
    rates = _TOKEN_COST.get(model)
    assert rates is not None, f"{model} missing from pricing table"
    assert rates["input"] > 0
    assert rates["output"] > 0


def test_compute_cost_uses_table_for_provider_model():
    cost = _compute_cost("gpt-5-mini", input_tokens=1000, output_tokens=1000)
    assert cost > 0


def test_record_llm_usage_writes_row_to_provided_session():
    db = MagicMock()
    added = []
    db.add.side_effect = lambda o: added.append(o)

    record_llm_usage(
        service="scan_chatgpt",
        model="gpt-5-mini",
        input_tokens=100,
        output_tokens=50,
        client_id=None,
        db=db,
    )

    assert len(added) == 1
    row = added[0]
    assert row.service == "scan_chatgpt"
    assert row.model == "gpt-5-mini"
    assert row.input_tokens == 100
    assert row.output_tokens == 50
    assert row.cost_usd > 0
    # When a session is provided, the caller owns the commit.
    db.commit.assert_not_called()


def test_scan_service_names_have_registered_prompt_version():
    from app.prompts.registry import get_version

    for svc in ["scan_chatgpt", "scan_perplexity", "scan_gemini", "scan_claude"]:
        assert get_version(svc) != "unknown", f"{svc} prompt version not registered"


def test_record_llm_usage_never_raises_on_bad_input():
    # Mirrors record_llm_call's contract: cost tracking must never break a scan.
    record_llm_usage(
        service="scan_chatgpt",
        model="gpt-5-mini",
        input_tokens=None,  # type: ignore[arg-type]
        output_tokens=None,  # type: ignore[arg-type]
        client_id=None,
        db=None,
    )


# ── Published-rate regression guards ─────────────────────────────────────────
# Verified 2026-09-04 against each provider's price sheet. Two rates were wrong
# before that check: Haiku 4.5 carried Haiku *3.5*'s $0.80/$2.50, and sonar's
# output was $1.00 instead of $2.50. Assert the exact figures so the next model
# swap has to update them deliberately rather than inherit stale ones.

_PUBLISHED_PER_MTOK = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
    "gpt-5-mini":                (0.25, 2.00),
    "sonar":                     (1.00, 2.50),
    "gemini-2.5-flash-lite":     (0.10, 0.40),
}

# USD per 1,000 searches / grounded requests, billed on top of tokens.
_PUBLISHED_SEARCH_PER_1K = {
    "claude-haiku-4-5-20251001": 10.00,
    "claude-sonnet-4-6":         10.00,
    "gpt-5-mini":                10.00,
    "sonar":                      5.00,
    "gemini-2.5-flash-lite":     35.00,
}


@pytest.mark.parametrize("model,expected", _PUBLISHED_PER_MTOK.items())
def test_token_rates_match_published_price_sheet(model, expected):
    from app.services.cost_tracker import _TOKEN_COST

    rates = _TOKEN_COST[model]
    assert rates["input"] * 1_000_000 == pytest.approx(expected[0])
    assert rates["output"] * 1_000_000 == pytest.approx(expected[1])


@pytest.mark.parametrize("model,expected", _PUBLISHED_SEARCH_PER_1K.items())
def test_search_rates_match_published_price_sheet(model, expected):
    from app.services.cost_tracker import _SEARCH_COST

    assert _SEARCH_COST[model] * 1_000 == pytest.approx(expected)


def test_every_priced_model_has_a_search_rate():
    # Every model we call runs search-enabled somewhere, so a token rate without
    # a matching search rate silently under-reports that model's spend.
    from app.services.cost_tracker import _SEARCH_COST, _TOKEN_COST

    assert set(_TOKEN_COST) == set(_SEARCH_COST)


def test_search_surcharge_is_added_on_top_of_tokens():
    # Gemini grounding ($0.035/prompt) dwarfs its token cost — the case that
    # made scan spend read ~100x low before the surcharge was modelled.
    tokens_only = _compute_cost("gemini-2.5-flash-lite", 1500, 500, 0)
    with_search = _compute_cost("gemini-2.5-flash-lite", 1500, 500, 1)

    assert float(with_search - tokens_only) == pytest.approx(0.035, abs=1e-9)
    assert with_search > tokens_only * 50


def test_unknown_model_warns_instead_of_silently_costing_nothing():
    # An added/renamed model must not make spend vanish without a trace.
    with patch("app.services.cost_tracker.logger") as mock_logger:
        cost = _compute_cost("some-unpriced-model", 1_000_000, 1_000_000)

    assert cost == 0
    mock_logger.warning.assert_called_once()
    assert mock_logger.warning.call_args[0][0] == "llm_cost_model_unpriced"


def test_record_llm_call_bills_anthropic_web_searches():
    from app.services.cost_tracker import record_llm_call

    response = MagicMock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.usage.server_tool_use.web_search_requests = 3

    db = MagicMock()
    added = []
    db.add.side_effect = lambda o: added.append(o)

    record_llm_call(
        service="assessment_brand_authority",
        model="claude-sonnet-4-6",
        response=response,
        client_id=None,
        db=db,
    )

    # 3 searches x $10/1k = $0.03, on top of the token cost.
    tokens = _compute_cost("claude-sonnet-4-6", 100, 50, 0)
    assert float(added[0].cost_usd - tokens) == pytest.approx(0.03, abs=1e-9)


def test_non_search_call_is_not_charged_a_search_fee():
    from app.services.cost_tracker import record_llm_call

    response = MagicMock()
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    # A plain MagicMock has no int here — the usual shape for non-search calls.

    db = MagicMock()
    added = []
    db.add.side_effect = lambda o: added.append(o)

    record_llm_call(
        service="digest_action",
        model="claude-haiku-4-5-20251001",
        response=response,
        client_id=None,
        db=db,
    )

    assert added[0].cost_usd == _compute_cost("claude-haiku-4-5-20251001", 100, 50, 0)


def test_every_logged_service_name_has_a_registered_prompt_version():
    """Generalises the scan-only check: no cost row may record version 'unknown'.

    position_extraction and toolkit_llms_full_txt both logged 'unknown' because
    they had no REGISTRY entry, so their spend could not be tied to a prompt.
    """
    import pathlib
    import re

    from app.prompts.registry import get_version

    names: set[str] = set()
    for path in pathlib.Path("app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        names.update(
            re.findall(r'record_llm_(?:call|usage)\([^)]*?service="([^"{]+)"', src, re.S)
        )

    assert names, "no record_llm_* call sites found — did the scan pattern break?"
    unregistered = sorted(n for n in names if get_version(n) == "unknown")
    assert unregistered == [], f"services logging an unknown prompt version: {unregistered}"
