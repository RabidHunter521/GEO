# SeenBy — Monthly Delivery Checklist

> Run this for every active client, every month.  
> One copy per client. Archive completed checklists in the client's folder.

---

## Client Info

**Client:** ___________________________  
**Tier:** ☐ Starter  ☐ Growth  ☐ Authority  
**Month:** ___________________________  
**Scan due by:** ___________________________  
**Report due by:** ___________________________  
**Faris sign-off:** ___________________________  

---

## Week 1 — Scan

- [ ] Open admin panel → `/clients/[id]/scan`
- [ ] Confirm all enabled platforms are still active (no toggle changes)
- [ ] Confirm competitor list is still accurate (no new competitors to add)
- [ ] Trigger on-demand scan
- [ ] Wait for scan to complete — check for platform errors in activity log (`/clients/[id]/activity`)
- [ ] If a platform failed: note it in the report, confirm scan still completed on remaining platforms
- [ ] If scan failed entirely: re-trigger once; if it fails again, flag to fix before proceeding

**Scan completed:** ☐ Yes  ☐ Partial (platforms failed: _________)  ☐ Failed (investigate)

---

## Week 2 — Review & Score Gating

- [ ] Open `/clients/[id]` — review the new GEO score vs. last month
- [ ] Check score movement: ☐ Up  ☐ Down  ☐ Flat
- [ ] Note score delta: previous _____ → current _____ (change: _____)
- [ ] **Gate Brand Authority score** — Claude suggestion reviewed; enter your approved number
- [ ] **Gate Content Quality score** — Claude suggestion reviewed; enter your approved number
- [ ] Verify label: "Based on public evidence · Reviewed by SeenBy" is showing on both manual dimensions
- [ ] Review competitor intelligence (`/clients/[id]/competitors`):
  - Any competitor overtaking client? ☐ Yes → alert sent ☐ No
  - Any notable new competitor mentions in AI? ___________________________
- [ ] Check for AI hallucinations or wrong brand info in raw results — flag if found
- [ ] Note 1–3 key findings to highlight in the report narrative

**Key findings this month:**
1. ___________________________
2. ___________________________
3. ___________________________

---

## Week 2 — Report Generation

- [ ] Go to `/clients/[id]/reports` → generate monthly PDF
- [ ] Confirm Claude "what changed this month" narrative was generated and looks accurate
- [ ] Read through the full PDF — check for:
  - [ ] Correct client name and brand throughout
  - [ ] Score bands using correct labels (not internal field names — see CLAUDE.md §2)
  - [ ] No "citation rate", "confidence score", "char offset", or other banned terms
  - [ ] Competitor takeaways are clear and client-friendly
  - [ ] Action items are specific and actionable (not generic)
- [ ] Make any edits needed before locking
- [ ] Confirm PDF is stored in R2 (check `/clients/[id]/reports` — link available)

**Report quality:** ☐ Send as-is  ☐ Minor edits made  ☐ Regenerated (reason: _________)

---

## Week 3 — Delivery

- [ ] Send monthly report delivery email (use template from `email-templates.md`)
  - Attach or link the PDF report
  - Include 1–2 personal sentences referencing what actually changed this month
  - Include the recommended next action
- [ ] Confirm email sent from `contact@seenby.my`
- [ ] Log delivery in activity log (or note here): ___________________________

**Delivered on:** ___________________________

---

## Week 3 — Proactive Touchpoints (if applicable)

- [ ] Score dropped 5+ pts → alert already sent; follow up with personal note on what's being done
- [ ] Competitor overtake → flag to client with context; suggest content/toolkit action
- [ ] Score improved 10+ pts → send a win email, use for upsell conversation
- [ ] Toolkit files not yet implemented → gentle nudge with implementation instructions link

---

## Week 4 — Account Health Check

- [ ] Invoice for next month issued and sent? ☐ Yes — due date: ___________
- [ ] Invoice paid? ☐ Yes  ☐ Pending  ☐ Overdue (follow up)
- [ ] Any upsell opportunity this month? ☐ Yes (what: _________)  ☐ No
- [ ] Client approaching end of Minimum Term (3 months)?
  - [ ] ☐ Yes — book a renewal conversation
  - [ ] ☐ No
- [ ] Any client complaints, feedback, or support requests this month? Note: ___________________________
- [ ] Anything to carry forward to next month? ___________________________

---

## Portfolio Overview (Monthly — Faris Only)

Run this once after all client checklists are done.

| Client | Tier | Score (prev → now) | Report Sent | Invoice Paid | Notes |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

**Total MRR this month:** RM ___________  
**API costs this month (check LLM cost ledger):** RM ___________  
**Net margin:** RM ___________  

**Anything to fix in the platform this month?** ___________________________  
**Any new leads from this month's activity?** ___________________________  
