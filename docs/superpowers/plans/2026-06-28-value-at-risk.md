# Value at Risk (Rung 2 — Money Estimator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show clinic owners a paired money story — "AI visibility got you ≈RM Y · ≈RM X still on the table" — on the client view, monthly PDF, and weekly digest.

**Architecture:** A new `estimate_value_at_risk` in `revenue_service` reuses the exact `estimate_pipeline` conversion chain (`visitor→lead→deal→close`), scaled by the visibility gap `(1−f)/f` with a 25% visibility floor and a 3× cap so the number stays conservative and never divides by zero. It returns `None` under the same discipline as `estimate_pipeline` (no deal value / no inputs ⇒ no number). Three surfaces add the at-risk figure beside the captured one.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Pydantic, pytest, WeasyPrint (PDF).

## Global Constraints

- At-risk math: `gap_multiplier = min((1 - f) / max(f, VALUE_AT_RISK_MIN_VISIBILITY), VALUE_AT_RISK_MAX_MULTIPLIER)`; `missed_visitors = V × gap_multiplier`; then the identical `estimate_pipeline` chain.
- `VALUE_AT_RISK_MIN_VISIBILITY = 0.25`, `VALUE_AT_RISK_MAX_MULTIPLIER = 3.0` — named constants in `app/core/constants.py` (no magic numbers, CLAUDE.md §3).
- `f` (visibility_frequency) is a fraction in [0,1] = `ai_citability / 100`.
- Return `None` unless `client.avg_deal_value_rm > 0` AND `ai_visitors is not None` AND `visibility_frequency is not None`. Conversion percentages fall back to `DEFAULT_VISITOR_TO_LEAD_PCT` (2) / `DEFAULT_LEAD_TO_CUSTOMER_PCT` (20).
- Never fabricate a money number; never show a half-number — the whole money block is hidden when an estimate is `None`.
- Approved language only (CLAUDE.md §2). Never surface confidence scores, char offsets, token counts, raw responses. All figures labeled estimates ("based on").
- All interpolated values in email/PDF HTML are `html.escape`-d.
- No DB migration — all `Client` fields already exist.
- Backend tests run from `backend/` with `pytest`.

---

### Task 1: `estimate_value_at_risk` + `ValueAtRisk` + constants

**Files:**
- Modify: `backend/app/core/constants.py` (near `DEFAULT_VISITOR_TO_LEAD_PCT`, line ~150)
- Modify: `backend/app/services/revenue_service.py`
- Test: `backend/tests/test_revenue_service.py`

**Interfaces:**
- Consumes: `DEFAULT_VISITOR_TO_LEAD_PCT`, `DEFAULT_LEAD_TO_CUSTOMER_PCT` (existing); `Client.avg_deal_value_rm`, `Client.visitor_to_lead_pct`, `Client.lead_to_customer_pct`.
- Produces:
  - `ValueAtRisk` dataclass: `ai_visitors: int, missed_visitors: int, missed_leads: int, missed_pipeline_rm: int, missed_won_rm: int, avg_deal_value_rm: int, visitor_to_lead_pct: int, lead_to_customer_pct: int, gap_multiplier: float`
  - `estimate_value_at_risk(ai_visitors: int | None, visibility_frequency: float | None, client: Client) -> ValueAtRisk | None`

- [ ] **Step 1: Add the two constants**

In `backend/app/core/constants.py`, directly after `DEFAULT_LEAD_TO_CUSTOMER_PCT: Final = 20`:

```python
# Value-at-risk model (rung 2). Floor visibility at 25% so a tiny score can't
# explode the gap multiplier; cap the multiplier at 3x so at-risk is never more
# than 3x captured. Both keep the estimate conservative. See revenue_service.
VALUE_AT_RISK_MIN_VISIBILITY: Final = 0.25
VALUE_AT_RISK_MAX_MULTIPLIER: Final = 3.0
```

- [ ] **Step 2: Write the failing tests**

In `backend/tests/test_revenue_service.py`, first check the top of the file for an existing `Client` stub/factory helper and reuse it. If none exists, add this helper near the top:

```python
from types import SimpleNamespace

def _client(avg_deal_value_rm=1000, visitor_to_lead_pct=None, lead_to_customer_pct=None):
    return SimpleNamespace(
        avg_deal_value_rm=avg_deal_value_rm,
        visitor_to_lead_pct=visitor_to_lead_pct,
        lead_to_customer_pct=lead_to_customer_pct,
    )
```

Then add these tests:

```python
from app.services.revenue_service import estimate_value_at_risk, ValueAtRisk


def test_value_at_risk_none_without_deal_value():
    assert estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=0)) is None
    assert estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=None)) is None


def test_value_at_risk_none_without_inputs():
    assert estimate_value_at_risk(None, 0.4, _client()) is None
    assert estimate_value_at_risk(100, None, _client()) is None


def test_value_at_risk_gap_multiplier_at_40pct():
    # f=0.4 -> (1-0.4)/0.4 = 1.5; V=100 -> 150 missed visitors.
    r = estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 1.5
    assert r.missed_visitors == 150
    # 150 visitors x 2% (default) = 3 leads; x RM1000 = RM3000 pipeline; x 20% = RM600 won.
    assert r.missed_leads == 3
    assert r.missed_pipeline_rm == 3000
    assert r.missed_won_rm == 600


def test_value_at_risk_full_visibility_is_zero():
    r = estimate_value_at_risk(100, 1.0, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 0.0
    assert r.missed_visitors == 0
    assert r.missed_pipeline_rm == 0


def test_value_at_risk_floors_low_visibility():
    # f=0.10 raw would be 9x; floored at MIN_VIS=0.25 -> (1-0.10)/0.25 = 3.6, capped to 3.0.
    r = estimate_value_at_risk(100, 0.10, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 3.0
    assert r.missed_visitors == 300


def test_value_at_risk_zero_visibility_no_divide_by_zero():
    r = estimate_value_at_risk(100, 0.0, _client(avg_deal_value_rm=1000))
    assert r is not None
    assert r.gap_multiplier == 3.0  # (1-0)/0.25 = 4.0, capped to 3.0


def test_value_at_risk_respects_custom_conversion_pcts():
    r = estimate_value_at_risk(100, 0.4, _client(avg_deal_value_rm=2000,
                                                 visitor_to_lead_pct=5,
                                                 lead_to_customer_pct=10))
    # 150 missed visitors x 5% = 7.5 -> round 8 leads; x RM2000 = RM15000; x 10% = RM1500.
    assert r.visitor_to_lead_pct == 5
    assert r.missed_pipeline_rm == 15000
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_revenue_service.py -k value_at_risk -v`
Expected: FAIL — `cannot import name 'estimate_value_at_risk'`.

- [ ] **Step 4: Implement**

In `backend/app/services/revenue_service.py`, add the import and the new unit. Update the constants import:

```python
from app.core.constants import (
    DEFAULT_VISITOR_TO_LEAD_PCT,
    DEFAULT_LEAD_TO_CUSTOMER_PCT,
    VALUE_AT_RISK_MIN_VISIBILITY,
    VALUE_AT_RISK_MAX_MULTIPLIER,
)
```

Add after `estimate_pipeline`:

```python
@dataclass
class ValueAtRisk:
    ai_visitors: int
    missed_visitors: int
    missed_leads: int
    missed_pipeline_rm: int
    missed_won_rm: int
    avg_deal_value_rm: int
    visitor_to_lead_pct: int
    lead_to_customer_pct: int
    gap_multiplier: float


def estimate_value_at_risk(
    ai_visitors: int | None, visibility_frequency: float | None, client: Client
) -> ValueAtRisk | None:
    """Estimate the pipeline missed because of AI invisibility, by scaling the
    realized visitor count by the visibility gap and running it through the same
    chain as estimate_pipeline. Conservative: visibility is floored at
    VALUE_AT_RISK_MIN_VISIBILITY and the gap multiplier capped at
    VALUE_AT_RISK_MAX_MULTIPLIER. None when the deal value or inputs are missing
    (we never invent a revenue number)."""
    deal_value = client.avg_deal_value_rm
    if not deal_value or deal_value <= 0 or ai_visitors is None or visibility_frequency is None:
        return None

    v2l = client.visitor_to_lead_pct if client.visitor_to_lead_pct is not None else DEFAULT_VISITOR_TO_LEAD_PCT
    l2c = client.lead_to_customer_pct if client.lead_to_customer_pct is not None else DEFAULT_LEAD_TO_CUSTOMER_PCT

    f = max(visibility_frequency, VALUE_AT_RISK_MIN_VISIBILITY)
    gap_multiplier = min((1.0 - visibility_frequency) / f, VALUE_AT_RISK_MAX_MULTIPLIER)
    gap_multiplier = max(gap_multiplier, 0.0)  # full visibility -> 0, never negative

    missed_visitors = ai_visitors * gap_multiplier
    missed_leads = missed_visitors * v2l / 100.0
    missed_pipeline = missed_leads * deal_value
    missed_won = missed_pipeline * l2c / 100.0

    return ValueAtRisk(
        ai_visitors=ai_visitors,
        missed_visitors=round(missed_visitors),
        missed_leads=round(missed_leads),
        missed_pipeline_rm=round(missed_pipeline),
        missed_won_rm=round(missed_won),
        avg_deal_value_rm=deal_value,
        visitor_to_lead_pct=v2l,
        lead_to_customer_pct=l2c,
        gap_multiplier=round(gap_multiplier, 4),
    )
```

Note on the floor: when `visibility_frequency=0.10`, `f=max(0.10,0.25)=0.25`, multiplier `=(1-0.10)/0.25=3.6` → capped to `3.0`. When `visibility_frequency=1.0`, numerator `(1-1.0)=0` → `0.0`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_revenue_service.py -v`
Expected: PASS — new tests plus all existing `estimate_pipeline` tests green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/constants.py backend/app/services/revenue_service.py backend/tests/test_revenue_service.py
git commit -m "feat(revenue): add estimate_value_at_risk gap-scaled model"
```

---

### Task 2: Client view overview shows the at-risk pair

**Files:**
- Modify: `backend/app/schemas/client_view.py` (`ClientViewTrafficValue`, line ~75-82)
- Modify: `backend/app/api/v1/client_view.py` (overview `traffic_value` block, line ~218-228)
- Test: `backend/tests/test_client_view.py` (or the existing client-view test module)

**Interfaces:**
- Consumes: `estimate_value_at_risk(ai_visitors, visibility_frequency, client)` and `ValueAtRisk` from Task 1.
- Produces: `ClientViewTrafficValue` gains `at_risk_leads: int | None`, `at_risk_pipeline_rm: int | None`, `at_risk_won_rm: int | None` (default `None`).

- [ ] **Step 1: Write the failing test**

In the client-view test module (match the existing overview-test style — they use a share token + TestClient, or a direct `get_overview` call with a mock db; reuse whichever the file already uses). Add a test asserting at-risk fields are populated when a deal value is set and a score + traffic exist, e.g.:

```python
def test_overview_traffic_value_includes_at_risk(client_with_score_and_traffic):
    # client has avg_deal_value_rm set, a GeoScore with ai_citability=40, and a
    # traffic snapshot with ai_visitors=100.
    resp = _get_overview(client_with_score_and_traffic)
    tv = resp["traffic_value"]
    assert tv["est_pipeline_rm"] is not None          # captured unchanged
    assert tv["at_risk_pipeline_rm"] is not None       # at-risk now present
    assert tv["at_risk_leads"] is not None
```

If the file has no reusable fixture producing a score + traffic + deal value, build the client/score/traffic rows inline following the file's existing setup pattern (GeoScore with `ai_citability=40.0`, one `AiTrafficSnapshot` with `ai_visitors=100`, `client.avg_deal_value_rm=1000`).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_client_view.py -k at_risk -v`
Expected: FAIL — `at_risk_pipeline_rm` not in the response (KeyError or None on a schema without the field).

- [ ] **Step 3: Extend the schema**

In `backend/app/schemas/client_view.py`, add to `ClientViewTrafficValue` after `est_won_rm`:

```python
    at_risk_leads: int | None = None
    at_risk_pipeline_rm: int | None = None
    at_risk_won_rm: int | None = None
```

- [ ] **Step 4: Populate in the overview**

In `backend/app/api/v1/client_view.py`, import the new function alongside the existing one:

```python
from app.services.revenue_service import estimate_pipeline, estimate_value_at_risk
```

(If the file currently imports `estimate_pipeline` from elsewhere, add `estimate_value_at_risk` to that same import.) Then replace the `traffic_value` block (~line 218-228) with:

```python
    traffic_value = None
    if traffic:
        latest_traffic = traffic[-1]
        est = estimate_pipeline(latest_traffic.ai_visitors, client)
        # f from the latest score's AI visibility (fraction). latest may be None
        # when no score exists yet — then at-risk is None too.
        vis_f = (latest.ai_citability / 100.0) if latest else None
        at_risk = estimate_value_at_risk(latest_traffic.ai_visitors, vis_f, client)
        traffic_value = ClientViewTrafficValue(
            period=latest_traffic.period,
            ai_visitors=latest_traffic.ai_visitors,
            est_leads=est.est_leads if est else None,
            est_pipeline_rm=est.est_pipeline_rm if est else None,
            est_won_rm=est.est_won_rm if est else None,
            at_risk_leads=at_risk.missed_leads if at_risk else None,
            at_risk_pipeline_rm=at_risk.missed_pipeline_rm if at_risk else None,
            at_risk_won_rm=at_risk.missed_won_rm if at_risk else None,
        )
```

(`latest` is the latest `GeoScore`, already computed earlier in `get_overview` as `history[0] if history else None`.)

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && pytest tests/test_client_view.py -v`
Expected: PASS — new test green, existing overview tests unaffected.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/tests/test_client_view.py
git commit -m "feat(client-view): add value-at-risk pair to overview traffic value"
```

---

### Task 3: Monthly PDF shows the at-risk pair

**Files:**
- Modify: `backend/app/services/report_service.py` (`ReportData` ~line 202; `_gather_report_data` ~line 498-534; the pipeline render block ~line 662-680)
- Test: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: `estimate_value_at_risk`, `ValueAtRisk` from Task 1.
- Produces: `ReportData.value_at_risk: ValueAtRisk | None` (default `None`); a new `at_risk_stat` HTML block inside the traffic section.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_report_service.py`, add a test on the HTML builder (unit, avoids WeasyPrint):

```python
def test_report_html_shows_value_at_risk_when_configured():
    from app.services.report_service import _build_report_html, ReportData
    from app.services.revenue_service import PipelineEstimate, ValueAtRisk
    client = MagicMock()
    client.name = "Acme Dental"
    data = _make_report_data()  # existing helper
    data.ai_visitors_current = 100
    data.pipeline = PipelineEstimate(100, 2, 2000, 400, 1000, 2, 20)
    data.value_at_risk = ValueAtRisk(100, 150, 3, 3000, 600, 1000, 2, 20, 1.5)
    out = _build_report_html(client, data)
    assert "RM 3,000" in out                     # at-risk pipeline rendered
    assert "still on the table" in out.lower()    # at-risk framing


def test_report_html_no_at_risk_block_when_none():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Dental"
    data = _make_report_data()
    data.value_at_risk = None
    out = _build_report_html(client, data)
    assert "still on the table" not in out.lower()
```

If `_make_report_data()` does not exist in the file, build a `ReportData` via the existing pattern other report-HTML tests in this file use, setting `pipeline` and `value_at_risk` explicitly.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_report_service.py -k value_at_risk -v`
Expected: FAIL — `ReportData.__init__` has no `value_at_risk` (or attribute error).

- [ ] **Step 3: Add the field + import**

In `backend/app/services/report_service.py`, update the revenue import (line ~42):

```python
from app.services.revenue_service import estimate_pipeline, PipelineEstimate, estimate_value_at_risk, ValueAtRisk
```

Add to `ReportData` after `pipeline: PipelineEstimate | None = None`:

```python
    # Pipeline estimated lost to AI invisibility this month, or None when unconfigured.
    value_at_risk: ValueAtRisk | None = None
```

- [ ] **Step 4: Populate in `_gather_report_data`**

After the existing `pipeline = estimate_pipeline(...)` (~line 498), add:

```python
    value_at_risk = estimate_value_at_risk(
        current_traffic.ai_visitors if current_traffic else None,
        (current_gs.ai_citability / 100.0) if current_gs else None,
        client,
    )
```

Then add `value_at_risk=value_at_risk,` to the `ReportData(...)` constructor (next to `pipeline=pipeline,`).

- [ ] **Step 5: Render the at-risk block**

In `_build_report_html`, immediately after the `pipeline_stat` block (~line 677, after the `else: pipeline_stat = ""`), add:

```python
    if data.value_at_risk is not None:
        r = data.value_at_risk
        at_risk_stat = f"""
  <div class="stat-box" style="background:#fffbeb;border-color:#fde68a;">
    <div class="stat-label">Estimated Pipeline Still On The Table</div>
    <div class="stat-value">RM {r.missed_pipeline_rm:,}</div>
    <div class="stat-sub">
      &asymp; RM {r.missed_pipeline_rm:,} in pipeline (~{r.missed_leads:,} potential customers)
      is estimated to be <strong>still on the table</strong> because AI does not yet
      recommend you as often as it could.
      <br><span style="color:#94a3b8;">Estimate based on your current AI visibility and
      the same deal value and conversion rates as above.</span>
    </div>
  </div>"""
    else:
        at_risk_stat = ""
```

Then add `{at_risk_stat}` to the `traffic_section` f-string (~line 679-681), right after `{pipeline_stat}`:

```python
    traffic_section = f"""
  <h2>AI Referral Traffic</h2>{visitor_stat}{pipeline_stat}{at_risk_stat}
"""
```

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_report_service.py -v`
Expected: PASS — new tests green, existing report tests unaffected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_report_service.py
git commit -m "feat(report): add value-at-risk pair to monthly PDF traffic section"
```

---

### Task 4: Weekly digest shows the paired money headline

**Files:**
- Modify: `backend/app/services/digest_service.py` (`DigestData` ~line 25-36; `_compute_digest_data` ~line 98-194; `_build_email_html`)
- Test: `backend/tests/test_digest_service.py`

**Interfaces:**
- Consumes: `estimate_pipeline`, `estimate_value_at_risk` from Task 1; `AiTrafficSnapshot` model.
- Produces: `DigestData` gains `captured_pipeline_rm: int | None`, `at_risk_pipeline_rm: int | None`, `at_risk_leads: int | None` (default `None`).

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_digest_service.py`, add a test on the HTML builder (it already has a `_data()`/`_make_digest_data()` helper — extend it with the new fields):

```python
def test_digest_html_shows_money_pair():
    htmlout = _build_email_html(_client(), _data(
        captured_pipeline_rm=2000, at_risk_pipeline_rm=3000, at_risk_leads=3,
    ))
    assert "RM 2,000" in htmlout                 # captured
    assert "RM 3,000" in htmlout                 # at-risk
    assert "on the table" in htmlout.lower()


def test_digest_html_no_money_block_when_unconfigured():
    htmlout = _build_email_html(_client(), _data(
        captured_pipeline_rm=None, at_risk_pipeline_rm=None, at_risk_leads=None,
    ))
    assert "on the table" not in htmlout.lower()
```

Update the test's `_data()`/`_make_digest_data()` helper to accept and pass these three new fields (default `None`).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_digest_service.py -k money -v`
Expected: FAIL — `DigestData.__init__` has no `captured_pipeline_rm`.

- [ ] **Step 3: Add the fields**

In `backend/app/services/digest_service.py`, add to `DigestData` after `proof_loss`:

```python
    captured_pipeline_rm: int | None = None
    at_risk_pipeline_rm: int | None = None
    at_risk_leads: int | None = None
```

- [ ] **Step 4: Load traffic + compute the pair in `_compute_digest_data`**

Add the model import at the top of the file (alongside the other model imports):

```python
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.services.revenue_service import estimate_pipeline, estimate_value_at_risk
```

Then, before the `return DigestData(...)` (after `proof_loss` is computed, ~line 181), add:

```python
    latest_traffic = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client.id)
        .order_by(AiTrafficSnapshot.period.desc())
        .first()
    )
    ai_visitors = latest_traffic.ai_visitors if latest_traffic else None
    captured = estimate_pipeline(ai_visitors, client)
    at_risk = estimate_value_at_risk(ai_visitors, current_citability / 100.0, client)
```

Then add to the `DigestData(...)` constructor:

```python
        captured_pipeline_rm=captured.est_pipeline_rm if captured else None,
        at_risk_pipeline_rm=at_risk.missed_pipeline_rm if at_risk else None,
        at_risk_leads=at_risk.missed_leads if at_risk else None,
```

(`current_citability` is the AI visibility percent already computed in this function and passed as `current_ai_citability`.)

- [ ] **Step 5: Render the money block in `_build_email_html`**

Add a money block near the proof block (after the `proof_block` is assembled). Show it only when both numbers exist; escape is unnecessary for ints but keep the structure consistent with the existing inline-style blocks:

```python
    money_block = ""
    if data.captured_pipeline_rm is not None and data.at_risk_pipeline_rm is not None:
        leads = data.at_risk_leads or 0
        money_block = f"""
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;
                    padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 6px;font-size:12px;color:#1d4ed8;font-weight:600;
                    text-transform:uppercase;letter-spacing:0.05em;">
            What AI visibility is worth
          </p>
          <p style="margin:0;font-size:15px;color:#1e3a8a;line-height:1.6;">
            AI visibility got you an estimated <strong>RM {data.captured_pipeline_rm:,}</strong>
            in pipeline this month. About <strong>RM {data.at_risk_pipeline_rm:,}</strong>
            (~{leads:,} potential customers) is still on the table.
          </p>
        </div>"""
```

Insert `{money_block}` into the email body f-string where the other blocks (e.g. `proof_block`) are interpolated — place it directly after `proof_block`.

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_digest_service.py -v`
Expected: PASS — new tests green, existing digest tests unaffected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/digest_service.py backend/tests/test_digest_service.py
git commit -m "feat(digest): add paired money headline to weekly email"
```

---

### Task 5: Full regression + language sweep

**Files:** test-only.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS (the one pre-existing unrelated rate-limit failure is already fixed on master; suite should be fully green). New money tests in revenue/client_view/report/digest all pass.

- [ ] **Step 2: Confirm no money number leaks without a deal value**

Run: `cd backend && pytest -k "value_at_risk or money or traffic_value" -v`
Expected: PASS — every "unconfigured" test asserts the block is absent / fields `None`.

- [ ] **Step 3: Language-rule grep on touched surfaces**

Run: `cd backend && grep -rnE "cited|uncited|citation rate|confidence score|char offset|token count" app/services/revenue_service.py app/services/digest_service.py app/services/report_service.py app/api/v1/client_view.py app/schemas/client_view.py || echo "clean"`
Expected: `clean`.

- [ ] **Step 4: Commit (if any fixups were needed)**

```bash
git add -A
git commit -m "test: regression sweep for value at risk"
```

---

## Self-Review

**Spec coverage:**
- Gap-scaled model + guardrails + gating → Task 1 ✅
- `MIN_VIS` / `MAX_MULT` constants → Task 1 ✅
- Client view overview pair → Task 2 ✅
- Monthly PDF pair → Task 3 ✅
- Weekly digest pair (+ traffic snapshot load) → Task 4 ✅
- Hidden when unconfigured / no half-number → asserted in Tasks 2-4 and Task 5 step 2 ✅
- Approved language / no fabricated number → Task 5 step 3 + gating tests ✅
- No migration → confirmed; no task creates one ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code; commands have expected output.

**Type consistency:** `estimate_value_at_risk(ai_visitors, visibility_frequency, client)` and `ValueAtRisk` field names (`missed_leads`, `missed_pipeline_rm`, `missed_won_rm`, `gap_multiplier`) are used identically across Tasks 2-4. `ClientViewTrafficValue` at-risk fields (`at_risk_leads`, `at_risk_pipeline_rm`, `at_risk_won_rm`) consistent between schema (Task 2 step 3) and population (Task 2 step 4). `DigestData` money fields consistent between Task 4 steps 3-5. `f = ai_citability / 100.0` used consistently in Tasks 2-4.
