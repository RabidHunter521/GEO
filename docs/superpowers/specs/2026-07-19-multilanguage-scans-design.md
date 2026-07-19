# Multi-Language Scans — BM + Chinese (Spec 7) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**⚠ Requires amending CLAUDE.md §11:** "Multi-locale prompts" is currently a
stop-and-confirm exclusion. This spec IS the confirmation request — no code
until Faris signs off and the §11 line is updated.

## Problem

Malaysia is a trilingual search market. A KL clinic's patients ask AI in Bahasa
Melayu ("klinik pergigian terbaik di KL") and Chinese ("吉隆坡最好的牙科诊所") —
and nobody, local or international, measures AI visibility in those languages.
Profound/Peec never will; this is SeenBy's structural moat. Today the scan
engine is English-only (`QUERY_TEMPLATES` in constants).

## Decisions

- **Score untouched — no SCORE_VERSION bump.** Non-English results are an
  additional *reporting* surface, not a score input. Folding languages into AI
  Citability would change the formula (bump + historical comparability break)
  and double-count platforms. Revisit only after months of ms/zh data exist.
  This is the single most important boundary in this spec.
- **Per-client language toggle**, default `["en"]` — cost control mirrors
  `enabled_platforms`. Enabling a language is an explicit per-client decision
  (BM for mass-market clients, zh for Chinese-community businesses).
- **Cap: languages × platforms multiplies scan cost.** en+ms+zh on 4 platforms
  ≈ 3× today's scan. Acceptable per-client because it's opt-in; the settings UI
  shows an estimated query count as the toggles change.
- **Templates are professionally reviewed, not machine-translated blind.**
  Claude drafts them; Faris (or a native reviewer) approves before they enter
  constants. Query quality IS the product here.
- **Brand detection risk is acknowledged up front:** `brand_detection` is
  deterministic regex on the brand name. Latin-script brand names usually appear
  as-is in BM/zh answers, so detection mostly holds — but Chinese answers may
  transliterate. v1 mitigation: optional per-client `brand_aliases` list fed
  into detection (also useful for English nicknames). No LLM detection.

## Design

### 1. Data model (one migration)

- `Client.enabled_languages: JSON` default `["en"]` (subset of
  `SCAN_LANGUAGES = ["en", "ms", "zh"]`).
- `ScanQueryResult.language: str` server_default `"en"` — existing rows correct
  automatically.
- `Client.brand_aliases: JSON | None` — optional alternate brand strings for
  detection (independent value; ships with this spec).

### 2. Constants

`QUERY_TEMPLATES_MS`, `QUERY_TEMPLATES_ZH`, `COMPETITOR_QUERY_TEMPLATES_MS/_ZH`
mirroring the English structure (4 categories × 5). City/industry interpolation
reviewed per language (word order differs — templates must read natively, not
as translated English). `PLATFORM×LANGUAGE` support map if any platform handles
a language poorly (start permissive; prune from evidence).

### 3. Scan engine

`query_builder` builds the standard set per enabled language (template table
keyed by language); the runner stamps `language` on result rows. Per-platform
isolation unchanged. Control queries (Spec 1) and pitch recipes (Spec 6) stay
English-only in v1.

### 4. Scoring guard

`scoring_service` filters `language == "en"` everywhere it aggregates — the
explicit guard that enforces the no-bump decision. Same filter in win/loss,
diff/flip, gap matrix, action center v1 (all English-only until each is
deliberately extended). Regression tests per consumer (the Spec 1/6 invariant
pattern, third instance — worth a shared test helper).

### 5. Surfaces (reporting-only v1)

| Surface | Content |
|---|---|
| Admin + client-view scan pages | Language filter/tabs; results grouped per language with the same Seen-by-AI presentation |
| Monthly PDF | "How AI answers in Bahasa Melayu / 中文" section: per-language visibility frequency + one proof card each, only when the language is enabled and has results |
| Weekly digest | One line when a non-en language is enabled: per-language visibility frequency |
| Client settings (admin) | Language toggles + estimated per-scan query count + brand_aliases field |

Client-facing labels: "Bahasa Melayu" and "中文 (Chinese)" — never ISO codes.

## Scope boundaries

**In scope:** migration, template tables (reviewed), builder + language
stamping, scoring/consumer guards + tests, brand_aliases in detection, the four
surfaces.
**Out of scope:** score integration (explicitly deferred); multi-language
content roadmap/briefs/toolkit generation; language-specific competitors;
Tamil (add when a client warrants it — the structure makes it a constants
change); translating the UI itself.

## Risks

- **Template quality** — a bad BM/zh query measures nothing. Mitigation: native
  review gate before merge; templates iterated from real scan responses in the
  first month.
- **Transliterated Chinese brand mentions missed** → undercounted visibility.
  Mitigation: brand_aliases; documented as a known v1 limitation in admin docs
  (never silently — an undercount presented as truth is the fabrication problem
  again).
- **Cost surprises** — mitigated by opt-in default `["en"]` + the query-count
  preview + existing budget_service caps.
- Platform capability drift (a platform answering zh poorly) — the support map
  gives a pruning lever without code change.

## Testing

- Builder: per-language sets built only for enabled languages; language stamped;
  competitor tracking queries per language.
- Guards: score/win-loss/diff outputs identical with and without ms/zh rows.
- Detection: alias matching; Latin brand in zh response detected.
- Surfaces: sections render only for enabled languages with data; sanitizer
  green; PDF section absent for en-only clients (zero regression).

## Success criteria

A client with BM enabled sees, on their portal and PDF, how often AI recommends
them when asked in Bahasa Melayu — with proof cards — while their GEO score and
all English analytics remain bit-identical to pre-feature behavior.
