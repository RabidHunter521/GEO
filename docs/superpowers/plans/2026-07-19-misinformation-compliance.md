# AI Misinformation Compliance Monitoring (Spec 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** First-class misinformation findings — verbatim AI quote, category, severity, admin review gate, corrective-action spawn into the existing remediation loop, re-scan candidate-fixed proof, and a "How AI represents you" PDF section.

**Architecture:** `MisinformationFinding` model; a post-scan best-effort detection service whose Claude candidates pass a server-side substring firewall (quote MUST exist verbatim in stored `response_text`); everything client-facing requires `confirmed`+ status (assessment-service pattern). Corrective actions reuse `RemediationItem` via a new item type.

**Tech Stack:** SQLAlchemy + Alembic (RLS), Claude API via the repo's prompt-registry conventions (seenby-prompts skill), FastAPI, pytest (Claude fully mocked), Next.js, WeasyPrint.

**Spec:** `docs/superpowers/specs/2026-07-19-misinformation-compliance-design.md`

## Global Constraints

- **The firewall is law:** no finding may be stored whose `quote` is not a normalized-whitespace substring of the source row's `response_text`. Rejected candidates are logged, never stored.
- Claude proposes; only Faris confirms. Nothing below `confirmed` reaches any client surface. Auto-checks produce `candidate-fixed` suggestions, never `verified_fixed`.
- `COMPLIANCE_RULES` is a Faris-maintained constants list; Claude cites rule keys from it, never invents regulations. All copy frames findings as "flags for your review", never "compliance certification".
- Detection runs post-commit best-effort (rollback + swallow) — a Claude failure never affects the scan.
- Quotes are copied onto findings at creation (findings outlive the 90-day `response_text` purge).
- Premium gating deferred (no plan column yet) — everything ships admin-visible; the only client surface is the PDF section (Faris-reviewed before sending anyway).
- Follow the seenby-prompts skill for the prompt file. Migration: `down_revision` = single current `alembic heads`. Branch: `feat/misinformation-compliance` off master.

---

### Task 1: Model + migration + rules constant

**Files:**
- Create: `backend/app/models/misinformation_finding.py`
- Modify: `backend/tests/conftest.py` (register model)
- Modify: `backend/app/core/constants.py`
- Create: `backend/alembic/versions/<newid>_add_misinformation_findings.py`
- Test: `backend/tests/test_misinformation_model.py`

**Interfaces:**
- Produces: `MisinformationFinding(id, client_id, scan_query_result_id, quote, category, rule_key, severity, explanation, status, detected_at, reviewed_at, resolved_at, admin_note)`; constants:

```python
MISINFORMATION_CATEGORIES: Final = ("wrong_service", "factual_error", "prohibited_claim", "outdated_info")
MISINFORMATION_SEVERITIES: Final = ("high", "medium", "low")
MISINFORMATION_STATUSES: Final = (
    "suggested", "confirmed", "dismissed", "corrected", "candidate_fixed", "verified_fixed",
)
# Compliance checklist for the medical niche (Faris-maintained; Claude may only
# cite keys from this dict — it never invents a regulation). Framing everywhere:
# "flags for your review", never "compliance certification".
COMPLIANCE_RULES: Final = {
    "guaranteed_results": "Claims guaranteeing treatment outcomes or cure",
    "superlative_medical": "Superlative medical claims (best/safest/painless) presented as fact",
    "unoffered_service": "Attributes a service/treatment the client does not offer",
    "wrong_credentials": "Misstates practitioner credentials or specialist status",
    "wrong_location_contact": "Wrong address, phone, or operating hours",
    "price_misquote": "States prices/promotions the client does not run",
}
```

- [ ] **Step 1: Failing test** — roundtrip, default status `suggested`, FK cascade to scan_query_result.
- [ ] **Step 2: Implement model** (fields per spec; `quote: Text` non-null, `category String(32)`, `rule_key String(64) nullable`, `severity String(8)`, `explanation Text`, `status String(24) default "suggested" server_default "suggested"`, datetimes; index on `client_id`). Migration with `ENABLE ROW LEVEL SECURITY`.
- [ ] **Step 3: PASS. `alembic heads` single head. Commit** — `feat(misinfo): finding model + compliance rules`

---

### Task 2: The substring firewall + prompt (detection core)

**Files:**
- Create: `backend/app/prompts/misinformation.py` (follow seenby-prompts conventions: VERSION, builder fn, explicit output contract)
- Create: `backend/app/services/misinformation_service.py` (pure firewall + candidate parsing first; Claude call isolated in one seam function)
- Test: `backend/tests/test_misinformation_firewall.py`

**Interfaces:**
- Produces:
  - `normalize_ws(text: str) -> str` — collapse runs of whitespace to single spaces, strip.
  - `quote_in_response(quote: str, response_text: str) -> bool` — normalized-substring check.
  - `parse_candidates(raw_json: str) -> list[Candidate]` — dataclass `(quote, category, rule_key, severity, explanation)`; invalid category/severity/rule_key → candidate dropped + logged.
  - `_call_claude(client, result) -> str` — the ONLY Claude seam (uses `anthropic_client()`/`MODEL`/`record_llm_call` exactly like `claude_action._generate_claude_action`).
- Prompt contract (in `prompts/misinformation.py`): input = response_text, client profile (name, industry, description, services from description, city/state, website), COMPLIANCE_RULES rendered as a keyed list; output = JSON array of `{quote, category, rule_key|null, severity, explanation}`; instructions REQUIRE quote to be copied verbatim from the response and rule_key to be one of the given keys or null.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_misinformation_firewall.py
from app.services.misinformation_service import normalize_ws, parse_candidates, quote_in_response

RESPONSE = "Klinik A offers laser\n  eye surgery and guarantees   full recovery."


def test_quote_in_response_normalizes_whitespace():
    assert quote_in_response("guarantees full recovery", RESPONSE)
    assert quote_in_response("laser eye surgery", RESPONSE)
    assert not quote_in_response("guarantees partial recovery", RESPONSE)


def test_parse_candidates_drops_invalid_enum():
    raw = '''[
      {"quote": "q1", "category": "prohibited_claim", "rule_key": "guaranteed_results",
       "severity": "high", "explanation": "e"},
      {"quote": "q2", "category": "made_up_category", "rule_key": null,
       "severity": "high", "explanation": "e"},
      {"quote": "q3", "category": "factual_error", "rule_key": "not_a_rule",
       "severity": "low", "explanation": "e"}
    ]'''
    kept = parse_candidates(raw)
    assert [c.quote for c in kept] == ["q1"]  # bad category and bad rule_key both dropped


def test_parse_candidates_tolerates_garbage():
    assert parse_candidates("not json at all") == []
```

- [ ] **Step 2: Run — FAIL. Implement** (`normalize_ws` via `" ".join(text.split())`; `parse_candidates` with json.loads in try/except, enum checks against the three constants, rule_key checked against `COMPLIANCE_RULES` keys when category == "prohibited_claim" — for other categories rule_key must be null or a valid key). Write the prompt builder.
- [ ] **Step 3: PASS. Commit** — `feat(misinfo): quote firewall + candidate parsing + prompt`

---

### Task 3: `detect(scan_id)` + post-scan wiring

**Files:**
- Modify: `backend/app/services/misinformation_service.py`
- Modify: `backend/app/services/scan_service.py` (post-commit block, after remediation sync)
- Test: `backend/tests/test_misinformation_detect.py`

**Interfaces:**
- Produces: `detect(scan_id, db) -> int` (count stored) — for each client-owned row of the scan that is (`hallucination_flagged` OR `brand_detected`), and not `is_control`/pitch (defensive getattr): call the Claude seam, parse, firewall-check each candidate against THAT row's `response_text`, dedupe against existing open findings for the client with the same normalized quote, store survivors as `suggested`. Never raises (internal try/except per row + outer).

- [ ] **Step 1: Failing tests** (mock `_call_claude`):
  - candidate whose quote passes firewall → stored `suggested` with quote copied;
  - candidate whose quote is NOT in response_text → not stored (and a `logger.warning` fired — assert via caplog or a rejected-counter return);
  - duplicate normalized quote against an existing `suggested`/`confirmed` finding → skipped;
  - `_call_claude` raising → `detect` returns 0, no raise;
  - competitor rows and non-flagged/non-detected rows → Claude never called for them.
- [ ] **Step 2: Implement; wire into `run_scan` post-commit:**

```python
        try:
            from app.services.misinformation_service import detect as detect_misinformation
            detect_misinformation(scan.id, db)
        except Exception as exc:
            db.rollback()
            logger.error("misinformation_detect_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 3: PASS + full scan suite. Commit** — `feat(misinfo): post-scan detection with verbatim-quote firewall`

---

### Task 4: Review workflow API + remediation spawn + re-scan candidate-fixed

**Files:**
- Modify: `backend/app/services/misinformation_service.py` — `review_finding(finding_id, action, db, note=None)` (`action ∈ confirm|dismiss`; stamps `reviewed_at`), `mark_corrected(finding_id, db)`, `resolve_finding(finding_id, db)` (`candidate_fixed → verified_fixed`, admin-only), `check_candidate_fixed(scan_id, db)` — for each `confirmed`/`corrected` finding of the scan's client: if no client-owned row in THIS scan contains the normalized quote, flip to `candidate_fixed` (stores nothing else; absence is a suggestion, not proof)
- Modify: `backend/app/core/constants.py` — `REMEDIATION_TYPES` gains `"misinformation"`
- Spawn: on `confirm`, create a `RemediationItem(item_type="misinformation", platform=<result.platform>, label=<result.query_text>, detail=<category label + rule text>)` via the existing dedupe constraint (get-or-create)
- Wire `check_candidate_fixed` into `detect`'s flow (same post-scan pass)
- Create: routes `backend/app/api/v1/misinformation.py` (`GET /clients/{id}/misinformation` queue incl. counts; `POST /misinformation/{id}/review` confirm/dismiss; `POST /misinformation/{id}/resolve`) + register in `router.py`
- Test: `backend/tests/test_misinformation_workflow.py`, `backend/tests/test_api_misinformation.py`

- [ ] **Step 1: Failing tests** — full state machine (suggested→confirmed→(remediation row exists)→candidate_fixed after a clean scan→verified_fixed via resolve; suggested→dismissed terminal; resolve rejects non-candidate_fixed); remediation sync does NOT auto-correct misinformation items (grounding: `remediation_service._sync_type` only touches the two existing types — verify and pin with a test).
- [ ] **Step 2: Implement services + thin routes. PASS. Commit** — `feat(misinfo): review workflow, remediation spawn, re-scan candidate-fixed loop`

---

### Task 5: Admin queue UI

**Files:**
- Modify: `frontend/src/app/clients/[id]/scan/ScanClient.tsx` — "How AI represents you — review queue" card (or a section on the client detail page if ScanClient is too crowded — decide in review; default: scan page, near the existing hallucination flag control)
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`

- [ ] **Steps:** queue card (finding rows: verbatim quote in quotation marks, category label, rule text, severity chip via 3-band colors, confirm/dismiss buttons, "mark corrected", resolve button on candidate_fixed) → `rtk lint && rtk tsc --noEmit` → browser-verify against seeded findings → commit — `feat(misinfo): admin review queue`

---

### Task 6: Client surfaces — PDF section + digest line + alert deep-link

**Files:**
- Modify: `backend/app/services/report_service.py` — "How AI represents you" section: counts by status (open = confirmed+corrected, fixed = verified_fixed), severity summary, and for each `verified_fixed` finding a before/after line: `AI previously said: "{quote}" — now corrected.` (mirror an existing optional section builder; section absent when no confirmed+ findings)
- Modify: `backend/app/services/digest_service.py` — one line only when a HIGH finding was confirmed in the past 7 days: `"We flagged and are correcting a high-priority statement AI made about {client name} — details in your monthly report."`
- Grounding+modify: `backend/app/services/alert_service.py` hallucination alert email — append a deep link to the client's scan-page queue
- Test: `backend/tests/test_misinformation_surfaces.py`

- [ ] **Step 1: Failing tests** — PDF section renders only with confirmed+ findings; `suggested`/`dismissed` never serialized anywhere client-facing (whitelist assertion); digest line only on new HIGH confirmed; all copy passes `language_sanitizer`; quotes HTML-escaped.
- [ ] **Step 2: Implement. Full suite. Commit** — `feat(misinfo): PDF "How AI represents you" + digest protection line`

---

### Task 7: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify.
- [ ] Walkthrough: seed a scan response containing a fabricated claim → detect (mocked Claude) → queue shows verbatim quote → confirm → remediation item appears → clean re-scan → candidate_fixed → resolve → PDF shows before/after. Then the firewall negative: mocked Claude returning an invented quote → nothing stored.
- [ ] Copy sweep: no "compliance certification"-style language anywhere; engagement-letter framing task flagged to Faris in PR description. Finish branch.

## Self-review notes

- Spec model/detection/workflow/surfaces → T1–T6; firewall is service-enforced (T2/T3), exactly per spec's hard rule.
- Deviation: added `candidate_fixed` as an explicit stored status (spec described it as a surfaced suggestion) — an unstored suggestion would be lost between sessions; status enum extended accordingly and reflected in constants.
- Client-view page surfacing deliberately absent (per spec: PDF-only until Premium gating exists).
