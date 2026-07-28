# SeenBy → Premier End-to-End GEO/AEO Company — Feature Ideas

Written 2026-07-11. Context: 5-phase retainer roadmap is the committed baseline
(Phase 1 Share-of-Source trend + flip detection in progress; Phases 2–5 specced).
This list is what comes AFTER/AROUND that roadmap, organized by strategic job.
Principle: everything a GEO retainer client needs, deliverable inside the app —
measure → diagnose → fix → publish → prove ROI.

## Tier 1 — Prove the money (what wins and keeps RM4-5k retainers)

1. **AI referral traffic attribution** — ingest GA4 (or a lightweight JS snippet)
   and segment traffic from chatgpt.com / perplexity.ai / gemini / copilot referrers.
   The single most persuasive retainer chart: "AI sent you 214 visitors this month,
   up 38%". Ties scans → visibility → actual clicks.
2. **Lead/conversion attribution** — a per-client tracked phone number or form
   UTM so AI-sourced visits become "AI brought you 6 leads worth ~RMx". This is
   the churn-killer.
3. **ROI dashboard on the share view** — score trend + AI traffic + leads on one
   page the client can check anytime. Retention through visibility of value.
4. **Before/after case-study generator** — one click compiles a client's 90-day
   story (score, queries won, flips, traffic) into a branded PDF/landing page.
   Sales asset factory for winning the NEXT client.

## Tier 2 — Close the loop (from "we told you what to fix" to "we fixed it")

5. **One-click publish** — WordPress/Shopify/Webflow integrations so roadmap
   articles and briefs publish (as drafts) directly from SeenBy. Today content
   dies in the gap between "generated" and "published".
6. **Schema auto-deploy snippet** — a small JS embed that injects the verified
   schema.json + keeps it updated from SeenBy, so clients who can't edit
   their site still get structured data. (Also: llms.txt hosting/proxy for
   clients who can't touch their web root.)
7. **Content refresh detector** — re-crawl on cadence, flag pages that lost
   AI visibility after a content change, or grew stale vs competitors.
8. **Hallucination correction workflow** — when a scan detects an AI stating
   something false about the client, generate the corrective actions (source-page
   fix, FAQ addition, GBP update, Wikidata edit) as a tracked task list with
   before/after re-scan proof. Nobody productizes this well yet.

## Tier 3 — Widen the measurement moat

9. **Google AI Overviews + Bing Copilot + Grok tracking** — the next platforms
   after the current 4. AI Overviews especially: it's where Malaysian SME buyers
   actually are (Google-dominant market).
10. **Prompt-volume intelligence** — enrich tracked queries with search-volume
    proxies so the roadmap prioritizes questions people actually ask, not just
    templates. (Keyword APIs / Google autocomplete mining.)
11. **Sentiment & framing analysis** — not just "seen by AI" but HOW: recommended
    vs. mentioned-with-caveats vs. warned-against. A sentiment flip is a bigger
    alert than a visibility flip.
12. **Cross-client industry benchmark index** — anonymized aggregate: "average
    dental clinic in KL is seen 34% of the time; you're at 61%". Unique data
    asset that compounds with every client and becomes marketing content
    ("SeenBy AI Visibility Index — Malaysia"), i.e. our own GEO play.
13. **Multi-language scans** — BM + Chinese query sets for the Malaysian market.
    Nobody local does this; instant differentiation. (Currently in §11 exclusions
    as multi-locale prompts — revisit post-MVP.)

## Tier 4 — Authority building as a service (the agency end-to-end promise)

14. **Source-level authority playbooks** — Phase 1 tells us WHICH sources AI
    cites (share-of-source). Next: per-source action plans — get listed on the
    directories/review sites/Reddit threads AI actually pulls from, tracked as
    tasks with verification crawls.
15. **Review orchestration** — Google review request flows (QR/links per client),
    since reviews are a top AI-trust signal. Track count/rating over time as
    Brand Authority evidence (fixes the assessment-evidence problem with real data).
16. **Digital PR / listicle placement tracker** — monitor the "best X in KL"
    articles AI cites, flag which ones the client is missing from, generate the
    outreach email.
17. **Wikipedia/Wikidata presence assistant** — eligibility check + draft
    entity data. High AI-weight, high-friction — perfect agency service.

## Tier 5 — Product & platform (scale beyond Faris)

18. **Client portal v2** — graduate the share view into a login-free but richer
    portal (already share-token gated): ROI dashboard, action status, content
    approvals ("approve this article" button → publishes).
19. **White-label / reseller mode** — other agencies run on SeenBy (post-MVP,
    §11 exclusion today; it's the scale path).
20. **Self-serve audit funnel** — free "How visible is your business to AI?"
    scan-lite as lead magnet: enter domain → 3 queries → teaser score → book a
    call. Engineering-as-marketing; feeds the retainer pipeline.
21. **Scheduled scans + anomaly alerts** (§11 exclusion today) — required for
    scale; on-demand doesn't survive 20 clients.
22. **Agent-readiness audit (AEO frontier)** — can an AI agent actually book/
      buy/contact on the client's site? WebMCP/actions readiness score. Early,
      but it's where AEO goes next; being first in-market matters.

## Sequencing recommendation

- Finish Phases 1–5 (retainer core) first — nothing above beats shipping the
  committed roadmap.
- Then Tier 1 (#1–3) — attribution is the strongest retention lever and mostly
  integration work, not research.
- Then #5 + #14 (close the content loop, weaponize share-of-source data you'll
  already have from Phase 1).
- #12 and #20 are the compounding marketing assets — start collecting the data
  early even if the UI comes later.
