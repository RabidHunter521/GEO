# SeenBy — Client P&L Tracker

> Build this in Google Sheets or Excel. Update monthly.  
> This is your business health dashboard — don't run blind.

---

## Tab 1: Client Roster

One row per active client. Update when a client changes tier, churns, or adds an add-on.

| Column | What to track |
|---|---|
| Client Name | Brand name |
| Tier | Starter / Growth / Authority |
| Start Date | When they signed |
| Minimum Term Ends | Start date + 3 months |
| Billing Cycle | Monthly / Annual |
| Setup Fee (one-time) | Actual amount charged |
| Monthly Retainer (RM) | Base retainer |
| Add-Ons (RM/mo) | Sum of any active add-ons |
| Total MRR (RM) | Retainer + add-ons |
| Status | Active / Churning / Churned / Paused |
| Churn Date | If churned |
| Notes | Any special terms, renewal flags |

**Formula: Total MRR = SUM of all active client [Total MRR] rows**

---

## Tab 2: Monthly Snapshot

Run this at the end of each month. Gives you the profit picture.

| Row | Column |
|---|---|
| **Revenue** | |
| Total MRR collected | Sum of retainers received this month |
| Setup fees this month | New client setup fees received |
| Add-on revenue | Any one-off extras billed |
| **Total Revenue** | Sum of above |
| | |
| **COGS (Direct Costs)** | |
| LLM API costs | Pull from the cost ledger in the admin panel |
| Cloudflare R2 | Monthly storage bill |
| Other platform costs | Perplexity API, Google API, OpenAI, etc. |
| **Total COGS** | Sum of API/infra costs |
| | |
| **Gross Profit** | Total Revenue − Total COGS |
| **Gross Margin %** | Gross Profit ÷ Total Revenue |
| | |
| **Operating Expenses** | |
| Tools & software | Bukku/Xero, Cal.com, email, any SaaS |
| Domain / hosting | Prorated monthly |
| Misc | Any other business costs |
| **Total OpEx** | Sum of operating expenses |
| | |
| **Net Profit** | Gross Profit − Total OpEx |
| **Net Margin %** | Net Profit ÷ Total Revenue |
| | |
| **Tax Set-Aside (24%)** | Net Profit × 0.24 — move to savings |
| **Founder Pay** | What you take home |

---

## Tab 3: Per-Client Profitability

Track each client's actual margin so you know who's profitable and who costs more than they pay.

| Column | What to track |
|---|---|
| Client | Name |
| Monthly Revenue | Their total MRR |
| API Cost/mo | Estimated LLM cost for their scans (from cost ledger) |
| Time Spent (hrs) | Your hours this month on this client |
| Time Value (RM) | Hours × your effective hourly rate |
| Gross Margin (RM) | Revenue − API Cost |
| Net Margin (RM) | Revenue − API Cost − Time Value |
| Net Margin % | Net Margin ÷ Revenue |

**Your effective hourly rate:** Total revenue ÷ total hours worked per month  
*(Recalculate quarterly as you scale)*

**Flag any client where net margin < 50% — either reprice, reduce scope, or build efficiency.**

---

## Tab 4: MRR Movement (Churn & Growth Tracking)

Track MRR changes month to month. This is the metric that tells you if the business is healthy.

| Column | What to track |
|---|---|
| Month | |
| Starting MRR | MRR at start of month |
| New MRR | New clients signed × their retainer |
| Expansion MRR | Upsells / add-ons from existing clients |
| Churned MRR | Lost client retainers |
| Ending MRR | Starting + New + Expansion − Churned |
| MoM Growth % | (Ending − Starting) ÷ Starting |
| Active Clients | Count of paying clients |
| Avg Revenue/Client | Ending MRR ÷ Active Clients |

**Healthy benchmark targets (early stage):**
- Churn rate < 5%/month (lose less than 1 in 20 clients monthly)
- MoM growth > 10% while below 10 clients
- Avg revenue per client trending up (upsells working)

---

## Tab 5: Tax & Cash

Simple view to make sure you're not caught off-guard at tax time.

| Column | What to track |
|---|---|
| Month | |
| Revenue collected | Actual cash in |
| Tax set-aside (24%) | Move this to a separate savings account |
| Business expenses paid | Total outgoings |
| Net cash this month | Revenue − Expenses |
| Cumulative cash balance | Running total |
| Tax savings balance | Running total of what you've set aside |

---

## Quick Setup Instructions

1. **Create a Google Sheet** with the 5 tabs above
2. **Tab 1** — add each client as you sign them
3. **Tab 2** — fill at month-end (30 min max)
4. **Tab 3** — fill alongside Tab 2; pull API cost from SeenBy's LLM cost ledger
5. **Tab 4** — automate with formulas referencing Tab 1 (or fill manually)
6. **Tab 5** — reconcile with your bank account monthly

**Time required:** ~45 min per month once set up.  
**What it tells you:** whether the business is actually profitable, which clients cost you money, and whether you're growing or leaking.

---

## Key Numbers to Watch

| Metric | Target | Red Flag |
|---|---|---|
| Gross margin | > 75% | < 60% |
| Net margin | > 55% | < 40% |
| Monthly churn | < 5% | > 10% |
| Avg client duration | > 6 months | < 3 months |
| Time per client/month | < 3 hours | > 5 hours |
| MRR vs. last month | Growing | Two months flat or declining |
