# SeenBy — Client Offboarding SOP

> Run this when a client gives notice or their contract ends.  
> Follow in order. Do not skip data steps — PDPA compliance depends on them.

---

## Trigger Events

This SOP applies when:
- Client sends written cancellation notice (30-day clock starts)
- Client fails to pay two consecutive invoices and SeenBy terminates
- Client's account is manually closed for any other reason

---

## Phase 1 — Acknowledge & Confirm (Day 0–2)

- [ ] Reply to the cancellation notice in writing (email from `contact@seenby.my`)
- [ ] Confirm the notice date and the **last active date** (notice date + 30 days)
- [ ] Confirm what final deliverables they're owed (any outstanding monthly report?)
- [ ] Log the cancellation in the admin panel — update client status to "Churning"
- [ ] Note reason for churn (if known): ___________________________

**Acknowledgement email template:**

> Hi [First Name],
>
> Thanks for letting me know. I've noted your cancellation request dated [date].
>
> As per our agreement, your service will remain active until [last active date — 30 days from notice]. You'll continue to receive [any outstanding report / weekly digests] during this period.
>
> I'll prepare a final summary for you before we close out.
>
> Irfan

---

## Phase 2 — Final Deliverables (Before Last Active Date)

- [ ] Run a final scan if one falls within the notice period (client has paid for it)
- [ ] Generate and deliver the final monthly PDF report
- [ ] Prepare a **"Where you ended up" summary** — a short table showing:
  - Baseline score (Month 1) vs. final score
  - Key wins during the engagement
  - Top unfinished recommendations (what they should continue pursuing)
- [ ] If toolkit files were generated: confirm client has copies (re-send if needed)
- [ ] If client view link is active: note it will be deactivated on close date

---

## Phase 3 — Final Invoice & Finance

- [ ] Confirm all outstanding invoices are settled
- [ ] If there is an overpayment (e.g. annual prepay with early exit): calculate pro-rata refund per contract terms and process
- [ ] Issue a final receipt / statement of account if requested
- [ ] Mark account as "Closed" in your accounting tool (Bukku / Wave / Xero)

---

## Phase 4 — Account Closure (On or After Last Active Date)

- [ ] Log into admin panel → `/clients/[id]/settings`
- [ ] Revoke the client view share link (if one was issued)
- [ ] Set client status to "Archived" (do NOT delete — data retention rules apply)
- [ ] Note the **archive date** — data must be retained for **6 months** from this date
- [ ] Set a calendar reminder for the data deletion date (archive date + 6 months)

**Data retention:**
- Raw scan responses: already auto-purged at 90 days (no action needed)
- Client profile, scores, reports: archived for 6 months, then permanently deleted
- PDF reports in R2: retained for 6 months, then deleted from R2

---

## Phase 5 — Exit Conversation (Optional but Recommended)

Within 2 weeks of close, send a short email:

> Hi [First Name],
>
> Now that we've wrapped up, I'd love to understand what could have been better.
>
> Two quick questions:
> 1. What was the most valuable part of working with SeenBy?
> 2. What's the main reason you decided to move on?
>
> No agenda — just genuine feedback so I can keep improving. And if the timing changes and you want to revisit, my door is always open.
>
> Irfan

- [ ] Email sent: ☐ Yes  ☐ Skipped (reason: _________)
- [ ] Feedback received: ___________________________
- [ ] Was churn preventable? ☐ Yes  ☐ No  ☐ Maybe — note what you'd do differently: ___________________________

---

## Phase 6 — Data Deletion (6 Months After Archive)

> Set a calendar reminder when you archive. Do not rely on memory.

- [ ] Calendar reminder fires (6 months post-archive)
- [ ] Confirm client is not reinstated / re-signed
- [ ] Delete client record from admin panel
- [ ] Delete associated PDF reports from Cloudflare R2
- [ ] Delete any local files (questionnaire, signed contract, correspondence) per your own data hygiene practice
- [ ] Log deletion date: ___________________________

---

## Churn Tracker (Running Log)

Keep a running record here or in your CRM:

| Client | Tier | Start Date | End Date | Duration | MRR Lost | Reason | Preventable? |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |

> Review this quarterly. Patterns in churn reason = your product/pricing signal.

---

## Re-Engagement (6–12 Months Later)

Some churned clients come back. Set a reminder to reach out with a relevant update:

> Hi [First Name],
>
> It's been [X months] — I wanted to share a quick update on AI search visibility in [their industry] in Malaysia, since things have shifted quite a bit.
>
> [1–2 relevant sentences — e.g., "Google Gemini now sources local business recommendations differently, and brands that have llms.txt implemented are getting cited 3x more often than those that don't."]
>
> Happy to run a fresh scan on [Brand Name] to show you where things stand — no obligation.
>
> Irfan

- [ ] Re-engagement email scheduled for: ___________________________
