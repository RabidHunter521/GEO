# AI Misinformation Compliance Monitoring (Spec 8) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

For a clinic, an AI stating something false — a treatment they don't offer, a
wrong address, an outcome claim they legally cannot make under Malaysian
medical-advertising rules (Medicines Advertisement Board regime) — is a
*liability* problem, not a marketing one. "We monitor how AI represents your
clinic and flag statements that create risk" is the Premium anchor
(`corepremium.md` already gates "AI misinformation monitoring" to Premium) and
justifies RM5k+ on a different budget than any visibility chart.

Today the machinery is partial: `ScanQueryResult.hallucination_flagged` (bool),
hallucination alerting in `alert_service`, and a remediation workflow
(`remediation_service` + `remediation_item`, already hallucination-aware). What's
missing: findings as first-class objects (what exactly did AI say, why is it a
problem, what severity), an admin review gate, a correction→re-scan proof loop,
and client-safe surfacing.

## Decisions

- **Every finding carries the verbatim AI quote.** A finding without an exact
  quote from stored `response_text` cannot exist — hard rule, enforced in the
  service, not the prompt. This is the direct answer to the prompt-audit
  fabrication problem: Claude proposes, but the evidence is a string the system
  verifies is present in the response.
- **Admin-gated end to end** (assessment_service pattern): detection creates
  `suggested` findings; nothing reaches any client surface until Faris confirms.
  A false "AI is lying about you" alarm would itself be misinformation.
- **Compliance categories are a reviewed rule list, not Claude's legal opinion.**
  Claude matches response text against a Faris-maintained checklist
  (`COMPLIANCE_RULES` — e.g. "guaranteed results claims", "superlative medical
  claims", "services not offered per client profile"). Claude never invents a
  regulation; the rule cited is from the list. Faris owns the list's legal
  accuracy (business responsibility, stated plainly).
- **Reuses the remediation workflow** for corrective actions rather than a
  parallel task system.
- **Premium gating deferred** until the `corepremium.md` plan column exists;
  ships admin-visible-only first, which is safe by construction.

## Design

### 1. Data model (one migration)

`backend/app/models/misinformation_finding.py`:

```
MisinformationFinding:
  id, client_id (FK CASCADE), scan_query_result_id (FK CASCADE),
  quote (Text — verbatim substring of the result's response_text),
  category ("wrong_service" | "factual_error" | "prohibited_claim" | "outdated_info"),
  rule_key (str|None — COMPLIANCE_RULES key for prohibited_claim),
  severity ("high" | "medium" | "low"),
  explanation (Text — one admin-facing sentence),
  status ("suggested" | "confirmed" | "dismissed" | "corrected" | "verified_fixed"),
  detected_at, reviewed_at (None until Faris acts), resolved_at, admin_note
```

### 2. Detection (extends the scan post-commit flow)

`misinformation_service.detect(scan_id)` — post-commit, best-effort (catch +
rollback + swallow, like the other post-commit steps):
- Runs only for rows already `hallucination_flagged` PLUS a compliance pass over
  brand-mentioned rows (a response can be visible AND non-compliant).
- Claude prompt (via seenby-prompts standards): given response_text, the client
  profile (services from description, address fields), and COMPLIANCE_RULES →
  candidate findings with exact quotes.
- **Server-side verification:** reject any candidate whose `quote` is not a
  substring of the stored `response_text` (normalized whitespace). Rejected
  candidates are logged, never stored. This check is the fabrication firewall.
- Stores survivors as `status="suggested"`. Existing hallucination alert email
  now links to the review queue.

### 3. Review + correction loop

- **Admin queue** (section on `/clients/[id]/scan` or client detail): suggested
  findings with quote, category, rule, severity → confirm / dismiss / edit
  severity+explanation.
- **On confirm:** offer to spawn remediation items (via `remediation_service`)
  from a per-category playbook — source-page fix, FAQ addition, GBP correction,
  schema/llms.txt update. Tracked like existing remediation.
- **Re-scan proof:** on each new scan, confirmed findings are auto-checked —
  if no result row for a similar query repeats the quote (normalized match),
  the finding is marked *candidate-fixed* and surfaced to Faris to flip to
  `verified_fixed` (admin gates the good news too; absence in one scan isn't
  proof). Before/after quote pair stored for the report.

### 4. Client-facing surfaces (confirmed+ findings only)

| Surface | Content |
|---|---|
| Monthly PDF | "How AI represents you" section: count of open/corrected findings, severity summary, and for `verified_fixed` items the before/after story ("AI previously said X — now corrected"). Quotes shown are client-safe by nature (they're what AI already says publicly), but wording passes `language_sanitizer`; internal fields never surface. |
| Client view | Premium-gated later; v1 = PDF only (keeps the public surface unchanged until gating exists). |
| Weekly digest | One line only when a HIGH finding was confirmed that week — protection reassurance, not alarm spam. |
| Alerts (existing) | Unchanged channel; now deep-links the queue. |

## Scope boundaries

**In scope:** model + migration, COMPLIANCE_RULES constant, detection service
with the substring firewall, admin queue UI, remediation spawn, re-scan
candidate-fixed loop, PDF section + digest line.
**Out of scope:** legal advice generation (rule list is Faris-maintained);
auto-outreach to platforms/OpenAI takedowns; client-view surfacing until plan
gating exists; non-medical rule packs (structure supports them via
COMPLIANCE_RULES keys, content later); monitoring outside scan responses (no
web-wide monitoring).

## Risks

- **False positives erode the premium promise** — the admin gate exists for
  exactly this; nothing client-facing without Faris.
- **Quote drift** (AI phrases the falsehood differently next scan) breaks the
  auto-check → that's why absence only produces *candidate-fixed*, never
  auto-verified.
- **Legal exposure of the rule list** — mitigated by framing everywhere as
  "flags for your review", never "compliance certification"; engagement-letter
  language is a business task, flagged here.
- 90-day raw-response purge: quotes are copied onto the finding at creation, so
  findings outlive `response_text` purging by design.

## Testing

- Firewall: candidate with non-substring quote rejected + logged; normalized
  whitespace matching; quote persisted independently of response purge.
- State machine: suggested→confirmed/dismissed; confirmed→corrected→
  candidate-fixed→verified_fixed transitions; reviewed_at/resolved_at stamps.
- Detection: runs post-commit best-effort (a Claude failure never affects the
  scan); only flagged/brand rows considered.
- Surfaces: PDF section absent when no confirmed findings; digest line only on
  new HIGH; sanitizer green; no internal fields in any payload.

## Success criteria

When an AI answer misrepresents a clinic, Faris sees the exact quote in a review
queue within one scan cycle, can confirm it, spawn tracked corrective actions,
and — after a later scan no longer shows the claim — the client's PDF tells the
before/after protection story with verbatim receipts. Nothing fabricated,
nothing client-facing without admin confirmation.
