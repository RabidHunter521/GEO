# backend/evals/run.py
"""Run the eval suites and compare them to the accepted baseline.

    poetry run python -m evals.run                        # offline suites only (no API key)
    poetry run python -m evals.run --live                 # + Claude-backed suites
    poetry run python -m evals.run --suite position_extraction --live
    poetry run python -m evals.run --live --update-baseline   # accept the current numbers

Exit code 1 when a gated metric regresses past the suite's tolerance, so the
same command works as a local check before a prompt change and in CI.
"""
import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from evals.suites import SUITES, SuiteResult, run_suite

BASELINES = Path(__file__).parent / "baselines.json"


def load_baselines() -> dict:
    return json.loads(BASELINES.read_text()) if BASELINES.exists() else {}


def regressions(result: SuiteResult, baseline: dict | None) -> list[str]:
    """Gated metrics that got worse than the baseline by more than the tolerance."""
    if not baseline:
        return []
    suite = SUITES[result.suite]
    out = []
    for gate in suite.gates:
        old = baseline["metrics"].get(gate.metric)
        new = result.metrics.get(gate.metric)
        if old is None or new is None:
            continue
        worse = (old - new) if gate.higher_is_better else (new - old)
        if worse > suite.tolerance:
            out.append(f"{gate.metric} {old} -> {new}")
    return out


def _print(result: SuiteResult, baseline: dict | None, regressed: list[str]) -> None:
    print(f"\n== {result.suite}  ({result.service} {result.prompt_version}, {result.model}, "
          f"{len(result.cases)} cases, dataset {result.dataset_hash})")
    for k, v in result.metrics.items():
        old = (baseline or {}).get("metrics", {}).get(k)
        print(f"   {k:<24} {v}" + (f"   (baseline {old})" if old is not None else ""))
    if baseline:
        if baseline.get("dataset_hash") != result.dataset_hash:
            print("   note: dataset changed since the baseline; compare with care")
        if baseline.get("prompt_version") != result.prompt_version or baseline.get("model") != result.model:
            print(f"   note: baseline was {baseline.get('prompt_version')} on {baseline.get('model')}")
    else:
        print("   no baseline yet: run with --update-baseline to accept these numbers")
    if result.usage.calls:
        print(f"   {result.usage.calls} model calls, ~${result.usage.cost_usd:.4f}")
    for f in result.failures:
        print(f"   FAIL {f.id}: expected {f.expected!r}, got {f.actual!r}")
    for r in regressed:
        print(f"   REGRESSION {r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", choices=sorted(SUITES), action="append",
                        help="run only this suite (repeatable); default: all that can run")
    parser.add_argument("--live", action="store_true", help="include suites that call Claude")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results to evals/baselines.json")
    parser.add_argument("--json", type=Path, help="also write full per-case results to this file")
    args = parser.parse_args(argv)

    names = args.suite or sorted(SUITES)
    live_requested = [n for n in names if SUITES[n].live]
    if live_requested and not args.live:
        if args.suite:
            parser.error(f"{', '.join(live_requested)} calls Claude: add --live")
        names = [n for n in names if not SUITES[n].live]
    if args.live and live_requested and not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
        parser.error("--live needs a real ANTHROPIC_API_KEY in the environment")

    baselines = load_baselines()
    results, failed = [], False
    for name in names:
        result = run_suite(name)
        regressed = regressions(result, baselines.get(name))
        failed |= bool(regressed)
        _print(result, baselines.get(name), regressed)
        results.append(result)

    if args.update_baseline:
        for r in results:
            baselines[r.suite] = {
                "prompt_version": r.prompt_version, "model": r.model,
                "dataset_hash": r.dataset_hash, "metrics": r.metrics,
            }
        BASELINES.write_text(json.dumps(baselines, indent=2, sort_keys=True) + "\n")
        print(f"\nbaseline updated: {', '.join(r.suite for r in results)}")
    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in results], indent=2, default=str))

    return 1 if failed and not args.update_baseline else 0


if __name__ == "__main__":
    sys.exit(main())
