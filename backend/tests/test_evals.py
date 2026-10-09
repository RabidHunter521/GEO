"""The eval harness (backend/evals): dataset integrity, the offline CI gate, and
the live suites' plumbing with Claude mocked.

The live suites themselves only run on demand (`python -m evals.run --live`);
here the model is mocked so CI proves the harness works without an API key.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from evals import run as eval_run
from evals.suites import SUITES, load_cases, run_suite


# ── dataset integrity ─────────────────────────────────────────────────────────

_REQUIRED = {
    "brand_detection": {"id", "source", "brand", "answer", "expected"},
    "position_extraction": {"id", "source", "brand", "answer", "expected"},
    "misinformation": {"id", "source", "client", "query", "answer", "expected_flags"},
}


@pytest.mark.parametrize("name", sorted(SUITES))
def test_dataset_is_well_formed(name):
    cases = load_cases(name)
    assert cases, f"{name} dataset is empty"
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), f"duplicate case ids in {name}"
    for c in cases:
        missing = _REQUIRED[name] - c.keys()
        assert not missing, f"{name}/{c['id']} missing {missing}"
        assert c["source"] in ("real", "synthetic")
        assert not c.get("needs_review"), f"{name}/{c['id']} was exported but never labelled"


def test_dataset_labels_have_the_right_types():
    assert all(isinstance(c["expected"], bool) for c in load_cases("brand_detection"))
    for c in load_cases("position_extraction"):
        assert c["expected"] is None or (isinstance(c["expected"], int) and c["expected"] > 0)
    for c in load_cases("misinformation"):
        for flag in c["expected_flags"]:
            # Every expected quote fragment must really be in the answer, or the
            # case could never pass the verbatim-quote firewall.
            assert flag["quote_contains"] in c["answer"], c["id"]


def test_every_suite_has_a_registered_prompt_version():
    from app.prompts.registry import REGISTRY

    for suite in SUITES.values():
        if suite.live:
            assert suite.service in REGISTRY, suite.name


# ── the offline gate CI enforces ──────────────────────────────────────────────

def test_brand_detection_does_not_regress_against_baseline():
    """A change to detect_brand_in_answer must not lower accuracy or break a
    regression case. Improving it is fine: re-run with --update-baseline."""
    result = run_suite("brand_detection")
    baseline = eval_run.load_baselines()["brand_detection"]
    assert result.metrics["regression_failures"] == 0, [f.id for f in result.failures]
    assert eval_run.regressions(result, baseline) == []


def test_regressions_respect_direction_and_tolerance():
    result = MagicMock(suite="misinformation", metrics={"recall": 0.80, "false_alarm_rate": 0.30})
    baseline = {"metrics": {"recall": 0.90, "false_alarm_rate": 0.20}}
    assert eval_run.regressions(result, baseline) == ["recall 0.9 -> 0.8", "false_alarm_rate 0.2 -> 0.3"]
    # Within the live tolerance (0.05): not a regression.
    result.metrics = {"recall": 0.87, "false_alarm_rate": 0.22}
    assert eval_run.regressions(result, baseline) == []
    assert eval_run.regressions(result, None) == []


def test_offline_run_skips_live_suites_without_flag(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(eval_run, "BASELINES", tmp_path / "baselines.json")
    assert eval_run.main([]) == 0
    out = capsys.readouterr().out
    assert "brand_detection" in out and "position_extraction" not in out


def test_live_flag_requires_a_real_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ci-not-a-real-key")
    with pytest.raises(SystemExit):
        eval_run.main(["--live"])


# ── live suites, model mocked ─────────────────────────────────────────────────

def _response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 5
    resp.stop_reason = "end_turn"
    return resp


def _client_replying(fn):
    client = MagicMock()
    client.messages.create.side_effect = lambda **kw: _response(fn(kw["messages"][0]["content"]))
    return client


def test_position_suite_scores_replies_and_tallies_cost_without_a_db():
    cases = {c["id"]: c for c in load_cases("position_extraction")}

    def reply(prompt):
        # Longest match wins: some answers are prefixes of others.
        hits = [c for c in cases.values() if c["answer"][:4000] in prompt]
        c = max(hits, key=lambda c: len(c["answer"]))
        return "none" if c["expected"] is None else str(c["expected"])

    from app.services import position_extraction as pe

    with patch.object(pe, "anthropic_client", return_value=_client_replying(reply)), \
         patch("app.services.cost_tracker.record_llm_call", side_effect=AssertionError("wrote to DB")):
        result = run_suite("position_extraction")

    assert result.metrics["accuracy"] == 1.0
    assert result.usage.calls == len(cases)
    assert result.usage.cost_usd > 0


def test_misinformation_suite_applies_the_quote_firewall():
    cases = load_cases("misinformation")

    def reply(prompt):
        for c in cases:
            if c["answer"] in prompt:
                flags = [{"quote": f["quote_contains"], "category": "factual_error", "rule_key": None,
                          "severity": "high", "explanation": "Wrong."} for f in c["expected_flags"]]
                # An invented quote on every case: the firewall must drop it, so
                # clean cases stay clean.
                flags.append({"quote": "a sentence the answer never said", "category": "factual_error",
                              "rule_key": None, "severity": "low", "explanation": "Invented."})
                return json.dumps(flags)
        return "[]"

    from app.services import misinformation_service as ms

    with patch.object(ms, "anthropic_client", return_value=_client_replying(reply)):
        result = run_suite("misinformation")

    assert result.metrics["recall"] == 1.0
    assert result.metrics["false_alarm_rate"] == 0.0
    assert result.metrics["fabricated_quote_rate"] > 0
    assert not result.failures



def test_export_anonymises_client_and_competitor_names():
    from evals.export_candidates import anonymise

    text = "ACME DENTAL beats Acme Dental Care and Bright Smile on price."
    out = anonymise(text, "Acme Dental", ["Bright Smile", "Acme Dental Care"])
    # The competitor whose name CONTAINS the client's must not become the client.
    assert out == "Placeholder Brand beats Competitor 2 and Competitor 1 on price."
