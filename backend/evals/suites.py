# backend/evals/suites.py
"""The eval suites: one per AI judgement step that moves a client's numbers.

Each suite loads its dataset, runs the REAL production function on every case
and scores the outcome. Nothing here re-implements the logic under test.

  brand_detection      offline  detect_brand_in_answer -> AI Citability (40% of the score)
  position_extraction  live     extract_position       -> AI Search Ranking
  misinformation       live     misinformation detection + quote firewall -> accuracy issues

Live suites call Claude and need ANTHROPIC_API_KEY. Their cost is collected in
memory instead of being written to llm_call_logs, so an eval run never touches
a database.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from unittest.mock import patch

DATASETS = Path(__file__).parent / "datasets"


@dataclass
class CaseResult:
    id: str
    passed: bool
    expected: object
    actual: object
    note: str | None = None


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class SuiteResult:
    suite: str
    service: str
    prompt_version: str
    model: str
    dataset_hash: str
    metrics: dict[str, float]
    cases: list[CaseResult]
    usage: Usage = field(default_factory=Usage)

    @property
    def failures(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.passed]


@dataclass(frozen=True)
class Gate:
    """A metric the baseline protects. higher_is_better decides the direction of a regression."""

    metric: str
    higher_is_better: bool


@dataclass(frozen=True)
class Suite:
    name: str
    service: str            # key in app.prompts.registry.REGISTRY
    live: bool
    gates: tuple[Gate, ...]
    # Allowed drop before a gated metric counts as a regression. Live suites
    # get a little slack: temperature 0 is near- but not fully deterministic.
    tolerance: float
    run: Callable[[list[dict], Usage], tuple[list[CaseResult], dict[str, float]]]


def load_cases(name: str) -> list[dict]:
    path = DATASETS / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dataset_hash(name: str) -> str:
    """Short content hash: a baseline only means something against the same cases."""
    return hashlib.sha256((DATASETS / f"{name}.jsonl").read_bytes()).hexdigest()[:12]


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 1.0


def _collect_usage(usage: Usage):
    """Stand-in for cost_tracker.record_llm_call: tally in memory, never write a DB row."""
    from app.services.cost_tracker import _compute_cost

    def _record(*, service, model, response, client_id=None, db=None, **_):
        u = response.usage
        usage.calls += 1
        usage.input_tokens += u.input_tokens
        usage.output_tokens += u.output_tokens
        usage.cost_usd += float(_compute_cost(model, u.input_tokens, u.output_tokens))

    return _record


# ── brand_detection (offline) ─────────────────────────────────────────────────

def _run_brand_detection(cases: list[dict], usage: Usage):
    from app.services.brand_detection import detect_brand_in_answer

    results = []
    for c in cases:
        actual = detect_brand_in_answer(c["answer"], c["brand"])
        results.append(CaseResult(c["id"], actual == c["expected"], c["expected"], actual, c.get("note")))

    by_id = {c["id"]: c for c in cases}
    seen = [r for r in results if r.expected is True]
    not_seen = [r for r in results if r.expected is False]
    metrics = {
        "accuracy": _ratio(sum(r.passed for r in results), len(results)),
        # Counted as Seen by AI when it was not: inflates AI Citability.
        "false_seen_rate": _ratio(sum(not r.passed for r in not_seen), len(not_seen)),
        # A real mention dropped: deflates AI Citability.
        "missed_seen_rate": _ratio(sum(not r.passed for r in seen), len(seen)),
        "regression_failures": sum(
            1 for r in results if not r.passed and by_id[r.id].get("regression")
        ),
    }
    return results, metrics


# ── position_extraction (live) ────────────────────────────────────────────────

def _run_position_extraction(cases: list[dict], usage: Usage):
    from app.services import position_extraction as pe

    results = []
    with patch.object(pe, "record_llm_call", _collect_usage(usage)):
        for c in cases:
            try:
                actual = pe.extract_position(c["answer"], c["brand"])
            except Exception as exc:  # one bad call must not sink the run
                actual = f"error: {exc}"
            results.append(CaseResult(c["id"], actual == c["expected"], c["expected"], actual, c.get("note")))

    ranked = [r for r in results if r.expected is not None]
    unranked = [r for r in results if r.expected is None]
    metrics = {
        "accuracy": _ratio(sum(r.passed for r in results), len(results)),
        "ranked_accuracy": _ratio(sum(r.passed for r in ranked), len(ranked)),
        # A position invented where the answer had none: a ranking the client never had.
        "false_position_rate": _ratio(sum(not r.passed for r in unranked), len(unranked)),
    }
    return results, metrics


# ── misinformation (live) ─────────────────────────────────────────────────────

def _quote_matches(expected_fragment: str, quote: str) -> bool:
    from app.services.misinformation_service import normalize_ws

    return normalize_ws(expected_fragment).lower() in normalize_ws(quote).lower()


def _run_misinformation(cases: list[dict], usage: Usage):
    import app.models  # noqa: F401 — registers every mapper so transient ORM objects build
    from app.models.client import Client
    from app.models.scan_query_result import ScanQueryResult
    from app.services import misinformation_service as ms

    results = []
    expected_total = found_total = 0
    clean_cases = false_alarms = 0
    candidates_total = fabricated = 0

    with patch.object(ms, "record_llm_call", _collect_usage(usage)):
        for c in cases:
            client = Client(id=uuid.uuid4(), **c["client"])
            row = ScanQueryResult(id=uuid.uuid4(), query_text=c["query"], response_text=c["answer"])
            try:
                candidates = ms.parse_candidates(ms._call_claude(client, row, db=None))
            except Exception as exc:
                results.append(CaseResult(c["id"], False, c["expected_flags"], f"error: {exc}"))
                continue

            # The production firewall: a quote that is not verbatim in the answer is dropped.
            kept = [k for k in candidates if ms.quote_in_response(k.quote, c["answer"])]
            candidates_total += len(candidates)
            fabricated += len(candidates) - len(kept)

            expected = c["expected_flags"]
            if expected:
                found = sum(
                    1 for e in expected if any(_quote_matches(e["quote_contains"], k.quote) for k in kept)
                )
                expected_total += len(expected)
                found_total += found
                passed = found == len(expected)
            else:
                clean_cases += 1
                false_alarms += bool(kept)
                passed = not kept

            actual = [{"quote": k.quote, "category": k.category, "rule_key": k.rule_key} for k in kept]
            results.append(CaseResult(c["id"], passed, expected, actual, c.get("note")))

    metrics = {
        # Real problems in an answer that the step surfaced for review.
        "recall": _ratio(found_total, expected_total),
        # Clean answers that still produced a flag: noise in the review queue.
        "false_alarm_rate": _ratio(false_alarms, clean_cases),
        # Quotes Claude invented, caught by the firewall. Informational only.
        "fabricated_quote_rate": _ratio(fabricated, candidates_total),
    }
    return results, metrics


SUITES: dict[str, Suite] = {
    "brand_detection": Suite(
        name="brand_detection", service="brand_detection", live=False, tolerance=0.0,
        gates=(Gate("accuracy", True), Gate("regression_failures", False)),
        run=_run_brand_detection,
    ),
    "position_extraction": Suite(
        name="position_extraction", service="position_extraction", live=True, tolerance=0.05,
        gates=(Gate("accuracy", True), Gate("false_position_rate", False)),
        run=_run_position_extraction,
    ),
    "misinformation": Suite(
        name="misinformation", service="misinformation_detection", live=True, tolerance=0.05,
        gates=(Gate("recall", True), Gate("false_alarm_rate", False)),
        run=_run_misinformation,
    ),
}


def _version_and_model(service: str) -> tuple[str, str]:
    from app.prompts.registry import REGISTRY
    from app.core.constants import SCORE_VERSION

    if service == "brand_detection":
        # Rule-based, not a prompt: the formula version it belongs to is SCORE_VERSION.
        return SCORE_VERSION, "rules"
    entry = REGISTRY[service]
    return entry["version"], entry["model"]


def run_suite(name: str) -> SuiteResult:
    suite = SUITES[name]
    usage = Usage()
    cases, metrics = suite.run(load_cases(name), usage)
    version, model = _version_and_model(suite.service)
    return SuiteResult(
        suite=name, service=suite.service, prompt_version=version, model=model,
        dataset_hash=dataset_hash(name), metrics=metrics, cases=cases, usage=usage,
    )
