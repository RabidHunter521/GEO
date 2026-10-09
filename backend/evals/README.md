# Evals

Unit tests mock the model, so they prove that a reply is *parsed* correctly,
not that the judgement is *right*. These suites run the real production
function for each AI judgement step that moves a client's numbers against a
labelled dataset, and score it.

| Suite | Production step | Moves | Runs |
|---|---|---|---|
| `brand_detection` | `detect_brand_in_answer` | AI Citability (40% of Growth Readiness) | Offline, on every CI run |
| `position_extraction` | `extract_position` (Claude) | AI Search Ranking | `--live`, on demand |
| `misinformation` | misinformation detection + quote firewall | Accuracy issues on the Reputation tab | `--live`, on demand |

## Running

```bash
cd backend
poetry run python -m evals.run                         # offline suites, no API key
poetry run python -m evals.run --live                  # all suites, needs ANTHROPIC_API_KEY
poetry run python -m evals.run --live --suite misinformation
```

Or from GitHub: Actions, **Live evals**, Run workflow (needs an
`ANTHROPIC_API_KEY` repository secret; a full run is about 30 Haiku calls).

Live runs never write to a database: cost is tallied in memory and printed.

## The baseline gate

`baselines.json` holds the last accepted numbers per suite, with the prompt
version, model and a hash of the dataset they came from. A run exits 1 when a
gated metric gets worse than the baseline (live suites allow 0.05 of slack,
since temperature 0 is not perfectly deterministic):

- `brand_detection`: `accuracy`, and `regression_failures` must stay 0
- `position_extraction`: `accuracy`, `false_position_rate`
- `misinformation`: `recall`, `false_alarm_rate`

**Before changing a scored prompt or its model:** run the suite on the current
version, make the change, run it again. If nothing regressed and you accept the
new numbers, re-run with `--update-baseline` and commit `baselines.json` with
the prompt change. The CI test `test_brand_detection_does_not_regress_against_baseline`
enforces the offline gate automatically.

## Datasets

`datasets/*.jsonl`, one case per line. Every case has `id`, `source`
(`real` = verbatim from a stored scan, `synthetic` = written to the shape of
real answers), and the correct label. `regression: true` marks a brand-detection
case that must always pass (a bug that already shipped once, or a core rule).

Labels follow the published methodology, not the current code. A case the code
gets wrong today stays in the dataset as a known failure: that is the point.

### Growing the dataset from real answers

`export_candidates.py` pulls stored answers, pre-filled with what production
decided and with client and competitor names replaced by placeholders:

```bash
railway ssh -s api -- python -m evals.export_candidates --suite brand_detection --limit 40
```

A person checks each `expected`, fixes the wrong ones, removes `needs_review`
and appends the row to the dataset. CI rejects rows still marked `needs_review`.
Adding cases changes the dataset hash, so re-baseline in the same commit.
