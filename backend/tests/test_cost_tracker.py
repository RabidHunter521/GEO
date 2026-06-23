# backend/tests/test_cost_tracker.py
from unittest.mock import MagicMock

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
