# Multi-Language Scans — BM + Chinese (Spec 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-client BM (`ms`) and Chinese (`zh`) query sets running alongside English on every scan, surfaced as reporting-only sections — with the GEO score and all English analytics bit-identical to pre-feature behavior.

**Architecture:** Language-keyed template tables + a `language` stamp on result rows + an English-only guard in every score/analysis consumer; `brand_aliases` extends deterministic detection for transliterated names.

**Tech Stack:** SQLAlchemy + Alembic, FastAPI, pytest, Next.js.

**Spec:** `docs/superpowers/specs/2026-07-19-multilanguage-scans-design.md`

## Global Constraints

- **GATE — Task 0 blocks everything:** CLAUDE.md §11 lists "Multi-locale prompts" as stop-and-confirm. No code before Faris signs off and §11 is amended in the same PR.
- Score untouched: NO SCORE_VERSION bump; `scoring_service` and every analysis consumer filter `language == "en"`.
- `SCAN_LANGUAGES = ("en", "ms", "zh")`; per-client `enabled_languages` default `["en"]`.
- Templates are Claude-drafted here but flagged for native review before merge (BM: Faris; zh: a native reviewer) — a review checkbox in the template task is a hard step.
- Client-facing labels: "Bahasa Melayu", "中文 (Chinese)" — never ISO codes.
- Control queries (Spec 1) and pitch recipes (Spec 6) stay English-only.
- Migration: `down_revision` = single current `alembic heads`. Branch: `feat/multilanguage-scans` off master.

---

### Task 0: Amend CLAUDE.md §11 (requires explicit Faris sign-off)

**Files:**
- Modify: `CLAUDE.md` §11 — change the "Multi-locale prompts" bullet to: `- ~~Multi-locale prompts~~ — shipped as per-client BM/Chinese scan languages (2026-07); score remains English-only, see spec 2026-07-19-multilanguage-scans-design.md`

- [ ] **Step 1: Confirm sign-off exists** (PR description or Faris's message referencing this plan). If not present, STOP — do not proceed to Task 1.
- [ ] **Step 2: Edit + commit** — `docs: lift §11 multi-locale exclusion for scan languages (score stays en-only)`

---

### Task 1: Migration + language columns + aliases

**Files:**
- Modify: `backend/app/models/client.py` (add `enabled_languages`, `brand_aliases` — mirror the `enabled_platforms` JSON pattern exactly)
- Modify: `backend/app/models/scan_query_result.py` (add `language`)
- Modify: `backend/app/core/constants.py` (`SCAN_LANGUAGES`, `LANGUAGE_LABELS`)
- Create: `backend/alembic/versions/<newid>_add_scan_languages.py`
- Test: `backend/tests/test_language_model.py`

**Interfaces:**
- Produces: `Client.enabled_languages: list` (JSON, default `["en"]`, server_default `'["en"]'`); `Client.brand_aliases: list | None` (JSON, nullable); `ScanQueryResult.language: str` (String(8), server_default `"en"`);

```python
SCAN_LANGUAGES: Final = ("en", "ms", "zh")
LANGUAGE_LABELS: Final = {"en": "English", "ms": "Bahasa Melayu", "zh": "中文 (Chinese)"}
```

- [ ] **Steps:** failing roundtrip test (defaults: `["en"]`, `"en"`, aliases None) → implement columns + migration (existing rows become `language="en"` via server_default — correct) → PASS → commit — `feat(lang): language columns + constants`

---

### Task 2: BM + zh template tables (native-review gated)

**Files:**
- Modify: `backend/app/core/constants.py`
- Test: `backend/tests/test_language_templates.py` (structure test: every language table has the same categories × 5 shape; competitor tables have all 4 keys; placeholders parse)

**Interfaces:**
- Produces: `QUERY_TEMPLATES_BY_LANGUAGE: Final[dict[str, dict]]` = `{"en": QUERY_TEMPLATES, "ms": QUERY_TEMPLATES_MS, "zh": QUERY_TEMPLATES_ZH}` and `COMPETITOR_QUERY_TEMPLATES_BY_LANGUAGE` likewise.

- [ ] **Step 1: Structure test** — for each language: 4 categories, 5 templates each, each template's placeholders ⊆ {brand, competitor, industry, location, city}; `"".format` smoke test with dummy values.
- [ ] **Step 2: Add drafts** (⚠ NATIVE REVIEW REQUIRED before merge — checkbox below):

```python
QUERY_TEMPLATES_MS: Final = {
    "brand": [
        "Ceritakan tentang {brand}",
        "{brand} terkenal dengan apa?",
        "Adakah {brand} pilihan yang baik?",
        "Apakah perkhidmatan yang ditawarkan oleh {brand}?",
        "Apa kata orang tentang {brand}?",
    ],
    "comparison": [
        "{brand} vs {competitor}",
        "Bandingkan {brand} dengan {competitor}",
        "{brand} atau {competitor}, mana lebih baik?",
        "{brand} vs {competitor}: mana patut saya pilih?",
        "Bagaimana {brand} berbanding {competitor}?",
    ],
    "recommendation": [
        "{industry} terbaik di {location}",
        "{industry} paling dipercayai di {location}",
        "Bagaimana nak pilih {industry} di {location}?",
        "Apa yang perlu dicari pada {industry} di {location}?",
        "Berapa kos {industry} di {location}?",
    ],
    "local": [
        "{industry} terbaik berdekatan saya di {city}",
        "{industry} paling popular di {city}",
        "{industry} mampu milik di {city}",
        "Macam mana nak cari {industry} yang boleh dipercayai di {city}?",
        "Tanda-tanda saya perlukan {industry} di {city}",
    ],
}

QUERY_TEMPLATES_ZH: Final = {
    "brand": [
        "介绍一下{brand}",
        "{brand}以什么闻名？",
        "{brand}是个好选择吗？",
        "{brand}提供什么服务？",
        "大家对{brand}的评价如何？",
    ],
    "comparison": [
        "{brand}和{competitor}哪个好",
        "比较{brand}和{competitor}",
        "{brand}还是{competitor}更好？",
        "{brand}和{competitor}我该选哪个？",
        "{brand}与{competitor}相比怎么样？",
    ],
    "recommendation": [
        "{location}最好的{industry}",
        "{location}最值得信赖的{industry}",
        "在{location}怎么选择{industry}？",
        "在{location}选{industry}要注意什么？",
        "{location}的{industry}收费大概多少？",
    ],
    "local": [
        "{city}附近最好的{industry}",
        "{city}评价最高的{industry}",
        "{city}价格实惠的{industry}",
        "在{city}怎么找可靠的{industry}？",
        "什么情况下我需要找{city}的{industry}？",
    ],
}

COMPETITOR_QUERY_TEMPLATES_MS: Final = {
    "brand":          "Ceritakan tentang {competitor}",
    "comparison":     "{competitor} vs {brand}",
    "recommendation": "Syarikat {industry} terbaik di {location}",
    "local":          "{industry} terbaik di {city}",
}
COMPETITOR_QUERY_TEMPLATES_ZH: Final = {
    "brand":          "介绍一下{competitor}",
    "comparison":     "{competitor}和{brand}哪个好",
    "recommendation": "{location}最好的{industry}公司",
    "local":          "{city}最好的{industry}",
}

QUERY_TEMPLATES_BY_LANGUAGE: Final = {
    "en": QUERY_TEMPLATES, "ms": QUERY_TEMPLATES_MS, "zh": QUERY_TEMPLATES_ZH,
}
COMPETITOR_QUERY_TEMPLATES_BY_LANGUAGE: Final = {
    "en": COMPETITOR_QUERY_TEMPLATES,
    "ms": COMPETITOR_QUERY_TEMPLATES_MS,
    "zh": COMPETITOR_QUERY_TEMPLATES_ZH,
}
```

Note for zh: `{industry}` interpolates the client's ENGLISH industry string into Chinese sentences — acceptable v1 (mixed-script queries are how Malaysian Chinese users actually type), but flag in the native-review pass. Bump `SCAN_QUERY_VERSION` in `query_builder.py` (`"v2"` → `"v3"`) since the template set changed — the constant's own docstring requires it.

- [ ] **Step 3: ⚠ NATIVE REVIEW checkpoint** — Faris reviews BM; a native zh speaker reviews zh. Record reviewer + date in a comment above each table. HARD GATE before merge (not before continuing dev).
- [ ] **Step 4: Run structure test — PASS. Commit** — `feat(lang): BM + zh query template tables (native review pending)`

---

### Task 3: Query builder + scan engine per language

**Files:**
- Modify: `backend/app/services/query_builder.py` — `build_client_queries(client, competitors, language="en")` and `build_competitor_queries(client, competitor, language="en")` select their tables from `*_BY_LANGUAGE[language]`; each returned dict gains `"language": language`
- Modify: `backend/app/services/scan_service.py` — `_run_platform_queries` loops `for language in _enabled_languages_of(client)` around both query loops, stamping `language=q["language"]` on rows; add `_enabled_languages_of(client)` mirroring `_enabled_platforms` (valid subset of `SCAN_LANGUAGES`, empty/legacy → `["en"]`)
- Test: `backend/tests/test_language_scan.py`

- [ ] **Step 1: Failing tests** — builder returns ms text for ms; scan with `enabled_languages=["en","ms"]` produces both `language` stamps and 2× client query rows; default client produces only en (row counts identical to pre-feature).
- [ ] **Step 2: Implement (backward-compatible default args — existing callers unaffected). Run scan suite. Commit** — `feat(lang): per-language query building + language-stamped results`

---

### Task 4: Brand aliases in detection

**Files:**
- Modify: `backend/app/services/brand_detection.py` — add `detect_brand_mention_any(response_text, brand_name, aliases: list[str] | None) -> bool` (True if the name OR any alias matches; keeps the cached single-name function untouched)
- Modify: `backend/app/services/scan_service.py` — client-row detection uses `detect_brand_mention_any(response_text, client.name, client.brand_aliases)`
- Test: `backend/tests/test_brand_aliases.py`

- [ ] **Steps:** failing tests (alias hit, no-alias fallback identical to old behavior, empty-string alias ignored) → implement → run detection + scan suites → commit — `feat(lang): brand alias detection`

---

### Task 5: The English-only guard (score + analysis invariant)

**Files:**
- Modify: `backend/app/services/scoring_service.py` — `compute_platform_breakdown` and `compute_ai_citability` legacy path filter `getattr(r, "language", "en") == "en"`
- Modify (query-level `.filter(ScanQueryResult.language == "en")`): `win_loss_service`, `digest_service` client_results, `remediation_service`, `gap_matrix_service`, `competitor_intelligence_service`, `scan_diff_service`, `proof_card_service` inputs, `headline_battle_service`, `report_service` per-query gathering, `client_view.py` scan-tab queries (en tab default), `causality_service` (if shipped), `index_service` (if shipped)
- Grounding: same `grep -rn "ScanQueryResult" backend/app` sweep as the control-query plan's Task 3 — the two invariants should end up co-located on the same lines; record the audited list.
- Test: `backend/tests/test_language_exclusion.py`

- [ ] **Step 1: Failing invariant tests** — with ms rows present: `compute_ai_citability` identical to en-only input; win/loss entries contain no ms query; digest seen/total counts unchanged.
- [ ] **Step 2: Implement. Full suite. Commit** — `feat(lang): en-only guard across score and analysis (no SCORE_VERSION bump)`

---

### Task 6: Surfaces + settings

**Files:**
- Modify: `backend/app/api/v1/scans.py` results listing — include `language`; `backend/app/api/v1/client_view.py` scan tab — group/filter by language, labels from `LANGUAGE_LABELS`
- Modify: `frontend/src/app/clients/[id]/scan/ScanClient.tsx` + `frontend/src/app/view/[token]/scan/page.tsx` — language tabs/filter (render only languages present in the data)
- Modify: `backend/app/services/report_service.py` — "How AI answers in Bahasa Melayu / 中文" section: per-language visibility frequency + one proof card each (reuse `select_proof_cards` on that language's rows), only when the language is enabled AND has results
- Modify: `backend/app/services/digest_service.py` — one line per enabled non-en language: `"In {label}: seen by AI {n} of {m} times this week."`
- Modify: settings — backend client-update schema + `SettingsForm.tsx`: language toggles (≥1 enforced, mirroring the platform-toggle pattern) + estimated per-scan query count preview + `brand_aliases` tag input
- Test: `backend/tests/test_language_surfaces.py` + client_view/report/digest test extensions

- [ ] **Steps:** failing surface tests (PDF section absent for en-only client — zero regression; digest line present only when ms enabled with results; client-view payload carries language labels not codes) → implement → full backend suite + `rtk lint && rtk tsc --noEmit` → browser-verify scan tab filtering → commit — `feat(lang): language surfaces + per-client toggles`

---

### Task 7: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify.
- [ ] Regression proof (the spec's success criterion): run the full backend suite on a seeded en-only client BEFORE and AFTER enabling ms — score, win/loss, digest counts bit-identical pre/post for the en-only case.
- [ ] Confirm native-review comments exist on both template tables (Task 2 gate).
- [ ] Finish branch.

## Self-review notes

- Spec §1–§5 mapped (migration→T1, constants→T2, engine→T3, guard→T5, surfaces→T6); brand aliases→T4.
- SCAN_QUERY_VERSION bump added (T2) — required by query_builder's own contract, missing from the spec; recorded as a spec addition.
- Cost preview in settings satisfies the spec's cap-visibility decision; hard cap not implemented (opt-in default + budget_service already bound cost) — matches spec.
