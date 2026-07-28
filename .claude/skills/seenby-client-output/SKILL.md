---
name: seenby-client-output
description: Quality rules for ANYTHING a SeenBy client can see — emails, PDF reports, share view pages, evidence bullets, action tips, generated content. Trigger when a task touches email templates, report/PDF generation, /view/* pages, digest copy, assessment evidence, or any LLM output surfaced to clients. Every confirmed demo bug so far lived on one of these surfaces.
---

# SeenBy Client-Facing Output Rules

Clients judge the whole product by these surfaces. All 7 confirmed walkthrough bugs (junk proof quotes, count mismatches, PDF period/header errors, silent report failure) were client-facing. Apply this checklist to every change on these surfaces.

## The surfaces

Email digests + monthly PDF reports, `/view/[token]/*` pages, evidence bullets shown in UI/PDF, LLM-generated tips/narratives/briefs/articles, toolkit files delivered to clients.

## Hard rules

1. **Language (CLAUDE.md §2)** — never cited/mentioned/citation rate/ranking position/visibility gap/confidence/token/char offset. Prompt-side instruction AND `sanitize_text()` on output. Grep the diff for banned words before commit (seenby-verify step 3).
2. **Every claim must be backed by data we actually hold.** No number, quote, or "fact" reaches a client unless it comes from a DB row, a crawl, a scan response, or a web-search result. LLM-asserted facts without a source are hallucinations waiting to be screenshotted. If a value is unknown, omit the sentence — never let the model fill it in.
3. **Numbers must reconcile.** If a page says "seen in 71 of 72 queries", both numbers must come from the SAME query set in the SAME scan. Off-by-one mismatches between headline and detail have shipped before — when showing a numerator and denominator, compute them in one place and pass both.
4. **Scores**: bands/labels from `SCORE_BANDS` (constants.py / score-utils.ts), colors from the 3-band traffic light — never hardcoded. Manual dimensions always carry "Based on public evidence · Reviewed by SeenBy".
5. **Share view (`/view/[token]`)**: whitelisted schemas only. Adding a field to an internal API is fine; adding it to a view serializer needs the question "should a client see this?" — confidence scores, offsets, raw AI responses, cost data: never. Invalid/revoked/archived tokens: uniform 404, no distinguishing errors.
6. **Failures must be loud to Faris, invisible to clients.** A report that fails to generate must alert (activity log + admin email), never send a broken/empty artifact. Check the error path actually notifies — silent failure is a known bug class here.
7. **Dates/periods**: PDF period labels and headers derive from the report row's period, not "now". Test with a report generated for a previous month.
8. **Proof quotes/snippets** shown to clients must be verbatim substrings of the stored raw response, trimmed at sentence boundaries — no mid-word cuts, no LLM paraphrase presented as a quote.

## Before claiming done

- [ ] Rendered the actual artifact (email HTML, PDF, share page) and looked at it — not just the JSON behind it
- [ ] Banned-language grep clean on the diff
- [ ] Numbers cross-checked against the DB rows that produced them
- [ ] Failure path exercised once (force an exception; confirm admin alert + no client artifact)
- [ ] `seenby-verify` passed; if this is pitch-related, also run `seenby-demo-check`
