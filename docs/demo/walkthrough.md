# SeenBy — The Complete Founder Walkthrough

*Written as if I (the founder) am walking you through every screen, every button, every number, and every formula — using our demo client **Medilink Healthcare** (GEO Score 60). Then, at the end, I take off the founder hat and put on the skeptical-investor hat and tear it apart.*

*Captured live from the running app on 5 July 2026 (admin panel, client view, scorecard PDF, and the full 6-page monthly PDF report), cross-checked against the backend source code so every number is traced to the exact formula that produces it.*

---

# Part 1 — What SeenBy Is and Why It Exists

SeenBy is an **agency-model AI visibility tracking platform**. The pitch to a client is one sentence: *"When your customers ask ChatGPT, Perplexity, Gemini or Claude 'who's the best clinic in KL?' — do you show up? We measure it, we prove it, and we fix it."*

The business model is deliberately **not** self-serve SaaS:

- **I (Faris) am the only admin.** There is no client login. Clients get a read-only share link and email deliverables.
- Scans are **on-demand** — I trigger them manually, typically monthly, matching the retainer cadence.
- The retainer (RM4,000+/month) is justified not by the software alone but by the **service wrapped around it**: human-reviewed scoring, content briefs, a 90-day content roadmap, remediation tracking, and a reviewed monthly PDF report.

The product vocabulary is strictly controlled. Clients never see machine-learning jargon:

| Internal concept | What the client sees |
|---|---|
| cited / mentioned | **Seen by AI** / **Not seen by AI** |
| citation rate | **visibility frequency** |
| ranking position | **AI Search Ranking** |
| visibility gap | **"Your competitors are winning here"** |
| confidence score, char offsets, token counts, raw API responses | never surfaced |

---

# Part 2 — The Numbers: Where Every Figure Comes From

Before touring the screens, here is the complete math, because every page reuses these numbers.

## 2.1 The query set (why "72 queries")

Each scan asks the same structured question set on every enabled platform. From `constants.py` (`QUERY_TEMPLATES`):

- **Brand** — 5 queries: "Tell me about Medilink Healthcare", "What is X known for?", "Is X a good choice?", "What services does X offer?", "What do people say about X?"
- **Comparison** — up to 5, **capped by number of competitors** (Medilink has 3, so 3): "Medilink vs Sentosa", "Compare Medilink and Care Clinic Group", "Is Medilink or Medipulse better?"
- **Recommendation** — 5: "Best {industry} in {location}", "Most trusted…", "How do I choose…", "What should I look for…", "How much does X cost…"
- **Local** — 5: "Best {industry} near me in {city}", "Top-rated…", "Affordable…", "How do I find a reliable…", "Signs I need a…"

That's **18 queries per platform** for Medilink (5+3+5+5) × **4 platforms** = **72 client queries per scan**.

On top of that, each competitor gets **4 tracking queries per platform** (1 per category) = 16 queries per competitor — which is why the Scan page shows "Competitor: Medipulse Healthcare — 16 queries".

## 2.2 "Seen by AI" — how detection works

Each query is sent to the real platform API, the raw answer is stored (retained 90 days), and detection is a **deterministic, case-insensitive, word-boundary-aware regex match** of the brand name in the response (`brand_detection.py`). No AI judges this step — it's reproducible and auditable. If "Medilink Healthcare" appears anywhere in the answer, the query is **Seen by AI**.

## 2.3 Visibility frequency (the platform percentages)

Per platform: `detected ÷ queries`. Medilink's ChatGPT card reads **50% · 9/18 queries** — ChatGPT's answers contained the brand in 9 of the 18 questions. The overall **44% (32/72)** is the same ratio across all platforms combined.

## 2.4 AI Citability (the 40% dimension) — currently 44

**Equal-weighted mean of per-platform visibility**: (50 + 39 + 50 + 39) ÷ 4 = 44.5 → 44. Platforms that fail entirely during a scan are marked *unavailable* and **excluded** from the average, so a provider outage never zeroes a client's score.

## 2.5 The Overall GEO Score — why Medilink is 60

From `scoring_service.compute_geo_score`, five weighted dimensions (SCORE_VERSION v1.2.0):

| Dimension | Weight | Medilink | Source |
|---|---|---|---|
| AI Citability | 40% | 44 | Automatic — scan engine |
| Brand Authority | 20% | 58 | Assisted — Claude-suggested, admin-reviewed |
| Content Quality | 20% | 55 | Assisted — Claude-suggested, admin-reviewed |
| Technical Foundations | 10% | 100 | Binary: toolkit files verified live → 100, else 0 |
| Structured Data | 10% | 100 | Binary: schema.json verified live → 100, else 0 |

`0.40×44 + 0.20×58 + 0.20×55 + 0.10×100 + 0.10×100 = 17.6 + 11.6 + 11 + 10 + 10 = 60.2 → 60`

**Score bands** (labels): 80–100 Excellent, 65–79 Good, **50–64 Fair**, 35–49 Developing, 0–34 Low.
**Colors** are a separate 3-band traffic light on the raw score: 0–29 red, 30–69 yellow, 70–100 green. So Medilink's 60 = "Fair" label, yellow/orange ring.

## 2.6 AI Search Ranking (the "#1.6" and "#2" figures)

For recommendation/local queries that come back as ranked lists ("1. Sentosa, 2. Medilink, …"), a Claude call reads the answer and extracts the brand's 1-based list position (`position_extraction.py`). It is additive — never replaces the binary Seen/Not-seen. The Scan page's **"#1.6 average AI Search Ranking across 17 ranked answers"** is the mean position over the 17 answers where Medilink appeared in a ranked list.

## 2.7 Recommended Action impact ("+7.8 GEO Score")

Actions are drafted by Claude after each scan, but **the impact number is computed server-side, never by Claude** (`action_center_service.py`): Claude only classifies effort (quick-win / medium-term / long-term → canonical fractions 0.40 / 0.20 / 0.08), then

`impact = fraction × (100 − dimension score) × dimension weight`, capped at 10, max 5 open actions.

Example: an AI Citability quick-win for Medilink ≈ 0.40 × (100−44) × 0.40 ≈ 9.0 points. Priorities: high ≥6, medium 3–5, low 0–2.

## 2.8 Pipeline estimate (the RM figures on the client view)

From `revenue_service.py` — never fabricated: it returns nothing unless I've set an average deal value for the client. With Medilink's settings (RM480 deal, 2% visitor→lead, 20% close) and June's 1,680 AI visitors (manually entered from the client's analytics):

- leads = 1,680 × 2% = **33.6 ≈ 34 leads**
- pipeline = 33.6 × RM480 = **RM16,128**
- est. won = × 20% = **RM3,226**

There's also a conservative **value-at-risk** model (pipeline missed due to invisibility): visibility floored at 25%, gap multiplier capped at 3×, so at-risk can never exceed 3× captured pipeline.

## 2.9 Win/Loss analysis

Only **recommendation + local** queries count (`WIN_LOSS_CATEGORIES`) — brand and comparison queries literally name the brands, which would poison a head-to-head signal. Each neutral query is bucketed: **Won** (you seen, no competitor), **Your competitors are winning here** (competitor seen, you not), **Shared** (both), **Open** (nobody).

---

# Part 3 — The Admin Side (my cockpit), page by page

## 3.1 Login (`/auth/login`)

Minimal card: SeenBy logo, "Admin access only", username + password, Sign in. NextAuth credentials flow; there is deliberately no signup, no password reset UI, no client login — this is a single-operator tool. All backend API calls are separately protected by a server-side bearer key the browser never sees.

## 3.2 All Clients (`/clients`) — the morning dashboard

This is home. Top to bottom:

- **Header**: "Clients — 7 clients · 1 prospect". Four buttons:
  - **Add Prospect** — create a lead with just a name + URL. Prospects get scanned and get a shareable view (that's my sales demo: "here's what AI already says about you"), but never get digests or reports.
  - **Add Client** — full client record.
  - **Scan clients** — bulk-trigger scans.
  - **Remove client** — bulk removal.
- **Stat strip**: **Clients 7** · **Average score 51** (mean of latest GEO scores) · **Improved 5** / **Declined 0** (vs each client's previous scan) · **Needs attention 1**.
- **Needs-attention banner**: NVD Asia (13) flagged for both *Low score* and *No scan in 30+ days*. This is my ops queue — it tells me who is at churn risk or overdue for their monthly scan.
- **Filters**: score band, industry, country, recency, plus a one-click **Scan due** filter (driven by each client's review cadence, default 30 days).
- **Client cards**: initials avatar, name, domain, score chip with delta (Medilink: **+6, 60**), industry, "Last scan 22 Jun 2026 · Next: 22 Jul 2026". "Scanning…" appears live while a scan runs. Clicking opens the client.
- **Prospects section**: each lead has *Copy view link* (send the teaser), *Convert* (promote to paying client), *Remove*.

## 3.3 Gap Matrix (`/clients/gap-matrix`)

One table, all active clients × the two neutral categories (**Recommendation**, **Local**), computed from each client's latest scan. Each cell: your visibility % vs the single strongest competitor. Medilink's row: Recommendation "You: 37% · Care Clinic Group: 75%", Local "You: 50% · Sentosa Healthcare: 75%", both stamped *"Your competitors are winning here."*

Why it exists: it's my **cross-portfolio triage view**. In ten seconds I see which client's retainer needs the most content work this month, and it doubles as sales ammunition ("every one of my clients has this gap — here's the plan").

## 3.4 Client Overview (`/clients/[id]`) — Medilink

- **Header** (repeated on all client pages): avatar, name, live site link, industry chip, and a **Client view** chip that opens their share-token page — I always check what the client sees before a call.
- **Score hero**: animated ring, **60 / 100**, band label **Fair**, one-line explainer ("How visible this client is across AI search…").
- **Seen by AI — by Platform**: four cards (ChatGPT 50% · 9/18, Perplexity 39% · 7/18, Gemini 50% · 9/18, Claude 39% · 7/18). This immediately shows *where* the problem is — Medilink is weakest on Perplexity and Claude.
- **Score Breakdown**: the five dimensions with weight and score. Each row is a **link to where you fix it**: AI Citability → Scan page; Brand Authority / Content Quality → Settings (with the full written justification shown inline, under the mandatory label *"Based on public evidence · Reviewed by SeenBy"*); Technical Foundations / Structured Data → Toolkit.
- **AI Visitors This Month**: "Awaiting entry" until I key in this month's number from the client's analytics (link jumps to Settings).
- **Recommended Actions**: up to 5 Claude-drafted, server-priced actions, each tagged with its dimension and *"Estimated Impact: +X GEO Score"* (see §2.7), with **Mark done** and **Dismiss**. For Medilink: publish health-screening explainers (+7.8), a Klang Valley local guide (+6.7), a corporate/occupational-health hub (+2.7), local press outreach (+2.1).
- Footer: "Score computed 22 Jun 2026, 06:17 am" — every number on this page is from that scan.

## 3.5 Checklist (`/clients/[id]/checklist`)

My **onboarding SOP baked into the product**: 26 default items across five phases — *Day 1 — Setup* (create record, add competitors, set cadence, toggle platforms, confirm categories, customize seed queries, trigger first scan), *Day 1–2 — First results review* (check hallucinations, review Claude actions, enter manual scores, confirm baseline, generate + verify toolkit, write first-scan narrative), *Day 2–3 — Delivery* (enable share link, send with a personal message, walk client through it), *Day 7 — First-week check*, *Ongoing* (digest, monthly PDF review). Items and sections are editable/addable/removable; progress is stored in my browser only — nothing here touches the client.

## 3.6 Scan & Visibility (`/clients/[id]/scan`) — the engine room

- **Run New Scan** — fires the 72+48-query scan across all enabled platforms (~2 min; retried once per API failure; one platform failing doesn't sink the scan — it's marked unavailable and excluded from the average).
- **Since last scan**: "Visibility frequency: 30.6% → 45.1% (+14.5 pts)", then two diff lists: **Newly Seen by AI (21)** and **Now Not seen by AI (11)**, each item tagged platform + category. This is the month-on-month story I tell the client: which exact questions we won and lost.
- **Platform summary cards** + platform filter buttons (All / ChatGPT / Perplexity / Gemini / Claude) which filter every table below.
- **Headline stats**: **32/72 queries seen (44%)** and **#1.6 average AI Search Ranking across 17 ranked answers**.
- **"Your Brand — 72 queries" table**: Platform · Category · Query · Status (**Seen by AI** with optional *AI Search Ranking #N* chip / **Not seen by AI**) · Actions:
  - **Share** — only on Seen rows: opens a 1200×630 dark social-card image ("SEEN BY AI — What ChatGPT said about Medilink Healthcare" + a verbatim quote + "Tracked by SeenBy"). Built for the client to post, and for me as marketing evidence.
  - **Flag** — mark the answer a hallucination; feeds Remediation and the admin alert email/Telegram.
- **Three competitor tables** (16 queries each) — the same view of what AI says about Sentosa, Care Clinic Group, Medipulse.
- **Remediation Progress**: every tracked hallucination and competitor-won query with a three-stage lifecycle — **Flagged → In progress → Corrected** — that I click through as work happens. Items **auto-correct when the next scan no longer shows the problem**, and *Sync to latest scan* pulls in new losses. The client sees this same list (sanitized) as "What We're Fixing" — it's the retainer's proof-of-work.

## 3.7 Competitor Intelligence (`/clients/[id]/competitors`)

- **Your AI visibility** card (44%) with per-platform chips, and a "2 competitors winning" warning chip.
- **Visibility frequency over time**: multi-line chart, one line per brand per scan (Medilink 31%→44%; Sentosa flat 69%; Care Clinic 56%; Medipulse 38%). This is the single most persuasive chart in a QBR: "you're climbing, Sentosa is static."
- **Win / Loss by Query** (neutral queries only, see §2.9): counts — **Won 5 · Your competitors are winning here 19 · Shared 12 · Open 3** — then the full card list for each bucket. Every losing card shows the exact query, platform, and *"Seen by AI instead: Sentosa Healthcare, Medipulse Healthcare"*.
  - On losing cards: **Generate content brief** — Claude writes a page brief (title, rationale, 5-section outline) designed to win that exact query back; **Regenerate** refreshes it. Two briefs already exist in the demo.
  - **Open — nobody seen yet** is flagged separately because those are the cheapest wins: no incumbent to displace.
- **Sources AI trusts in your category** (Share-of-Source): captures which domains Perplexity actually leaned on when answering, classifies them (client-owned / competitor-owned / third-party), and fetches third-party pages to check which brands appear there — i.e., *the acquisition list for where to get mentioned*. In this demo it shows "No source data yet. Run a scan" because Medilink's seeded scan predates the feature.
- **Per-competitor cards**: name, URL, visibility %, "winning here" flag, per-platform percentages annotated "· winning here", and a 16-cell platform×category grid of Seen/Not-seen — the full anatomy of each rival.

## 3.8 AI Readiness Toolkit (`/clients/[id]/toolkit`)

Three Claude-generated files in tabs, each with **Copy** and **Download**, plain-English implementation instructions, the expected URL, and a **live status** chip:

1. **llms.txt** (Answer.AI spec) — a structured brand summary for AI crawlers. Medilink's is fully populated from the Settings profile: about, services, clinics, contact.
2. **schema.json** — JSON-LD (LocalBusiness + Organization + FAQPage).
3. **robots.txt** — explicitly allows GPTBot, PerplexityBot, ClaudeBot, Google-Extended.

**Verify live** re-crawls `medilinkhealthcare.my/llms.txt` etc.; on success the Technical Foundations and Structured Data dimensions flip to 100 automatically (20% of the GEO score). **Regenerate** rebuilds files after profile changes. Medilink: all three *Verified live*.

## 3.9 Content Gaps (`/clients/[id]/content-gaps`)

"Last analysed Jun 22, 2026 · **27 pages crawled**" — we crawl the client's site and have Claude map it against the industry's topic space:

- **Missing topics (3)** — condition/symptom guides, patient guides, competitor comparisons. Biggest opportunities.
- **Weak topics (2)** — health-screening explainers, occupational health. Mentioned but thin.
- **Strong topics (1)** — clinic locations & hours.
- **Suggested content ideas** — three concrete titled pieces, each with the *why* tied to which competitor currently wins that query type.
- **Entity coverage — 3/6 · 56%** — the concepts AI associates with the industry (Health Screening Packages ✓, GP Consultation ✓, Clinic Locator ✓, Occupational Health ○, Corporate Panel ○, Vaccination ○). Covering these helps AI *recognize* the brand in-category.
- **Content quality signals** — hard crawl stats: 6,800 words, 21 H1s, 4 FAQ sections, 1 blog page, structured data: None (on-page).
- **SeenBy content recommendation** — one synthesized paragraph, which also appears in Settings as the informational aid for my Content Quality score.

## 3.10 Content Roadmap (`/clients/[id]/content-roadmap`)

"A prioritized 90-day plan of 12 weekly content pieces, built from the questions where your competitors are winning" — generated Jun 22 *from 20 lost queries*. Each week card: priority (high/medium), content type ("Service explainer pages"), a clickable article title (**Write article** drafts the full piece with Claude), the strategic rationale, and *"Your competitors are winning here: …"* naming who it displaces. The demo currently shows Weeks 1–3.

## 3.11 Reports (`/clients/[id]/reports`)

- **Scorecard PDF** — instant one-pager (see Part 4.1), generated fresh from the latest scan, never stored.
- **Generate Report** — queues the monthly report on the Celery worker: gathers scan data → renders HTML → WeasyPrint PDF → uploads to Cloudflare R2 (never stored in Postgres) → listed here for **my review before sending** to the client (send marks `sent_at`, and only then does it appear in the client view). Reports are never generated for prospects. Download links are freshly-signed R2 URLs that expire.

## 3.12 Activity Log (`/clients/[id]/activity`)

Newest-first audit trail of everything: client onboarded → scan completed (with score) → toolkit generated → toolkit verified → share link generated → traffic snapshot recorded → content gaps analyzed → briefs generated → hallucination flagged. My memory and my paper trail if a client ever asks "what did you actually do in May?"

## 3.13 Settings (`/clients/[id]/settings`)

Everything configurable, in order:

- **Brand Details** — name, website, industry (drives query templates).
- **Profile** — description, target audience, country/state/city (drives {location}/{city} in queries), contact email (digest + report recipient), logo (client-view header). Explicitly noted: "These fields power the AI Readiness Toolkit generator."
- **Manual Score Inputs** — Brand Authority (58) and Content Quality (55), each with a **Generate assessment** button (Claude drafts a suggested score + evidence from public signals; I accept or adjust — the human always gates the number), plus **required** written justifications ("never leave it blank with a score set") because they're shown to the client under the evidence label. Also: score-drop alert threshold (35) and review cadence (30 days). The latest Content Gaps recommendation is displayed here as an informational aid.
- **Scan Platforms** — the four toggles; at least one required; fewer platforms = cheaper scan, narrower picture.
- **Competitors (3/5)** — live add/remove (effective immediately), max 5.
- **AI Referral Traffic** — monthly manual entry of AI-referral visitors (June 1,680; May 1,320); informational only, never affects the GEO score. Below it, the **Pipeline value estimate** inputs: avg deal RM480, visitor→lead 2%, close 20% (see §2.8).
- **Client View Link** — the full share URL with Copy / Open / **Regenerate** (invalidate + reissue) / **Revoke**. 256-bit token; invalid or revoked tokens get a uniform 404.
- **Internal notes** — admin-only scratchpad.
- **Danger Zone** — Archive client (data retained 6 months post-churn, then auto-deleted).

## 3.14 Emails and alerts (no UI page, but part of the product)

- **Weekly digest** (automated, from contact@seenby.my): subject is human-first but always contains the score — *"Medilink Healthcare: seen by AI in 32/72 questions this week · GEO Score 60"*. Body: score + trend, a Claude-generated action **only when the score moved ±5pts** (otherwise a static band-appropriate tip), verbatim win/loss proof cards, captured + at-risk pipeline figures, the headline battle, and the share-link CTA. Idempotent — never twice in 6 days. Never sent to prospects.
- **Admin alerts** (score drop below threshold, competitor overtake, hallucination flags): always emailed to contact@seenby.my, plus Telegram push when configured; best-effort — an alert failure never breaks a scan.

---

# Part 4 — The PDFs

## 4.1 The one-page AI Visibility Scorecard

Header "SeenBy · AI Visibility Scorecard · date". Dark score block (**60 · GEO SCORE · FAIR**) beside the headline *"Seen by AI in 32 of 72 buyer questions"*. Four platform cards (% + status). A **"What changed"** box: *"Your overall score rose from 55 to 60 this month…"*. Footer: "AI visibility across ChatGPT, Perplexity, Gemini and Claude. Tracked by SeenBy · contact@seenby.my". Purpose: the thing a client forwards to their boss.

## 4.2 The Monthly PDF Report (6 pages, WeasyPrint, reviewed before sending)

**Page 1 — Cover.** Dark navy, "SeenBy — AI VISIBILITY INTELLIGENCE", "MONTHLY AI VISIBILITY REPORT — Medilink Healthcare — July 2026", a semicircular gauge (60 · GEO SCORE · FAIR, orange arc = yellow band), and the **"what changed" narrative** — Claude-written at build time, persisted on the report; falls back to a deterministic sentence if generation fails. Footer on every page: client · period · "Confidential" · page N of 6.

**Page 2 — Score.** Green trend banner ("↑ Score improved from 55 to 60"), big score, **Score Trend bar chart** (one bar per scan: 55 → 60), then **"What AI said about you"** — verbatim proof quotes: green-bordered "SEEN BY AI · CHATGPT / PERPLEXITY" cards and an orange **"WHO CHATGPT RECOMMENDED INSTEAD"** card quoting the competitor. Evidence, not claims.

**Page 3 — Breakdown.** All five dimensions as labeled horizontal bars with score, weight, and sourcing line (Automatic — scan engine / Based on public evidence · Reviewed by SeenBy with the full justification text / Automatic — Toolkit verified). Then **AI Visibility Frequency: 32/72** and the platform breakdown table (platform · % · status).

**Page 4 — Money and war.** **AI Referral Traffic** (this month's visitor number, or "Tracking begins soon" when not yet entered). **The Battle to Win Next** — the single highest-value lost query, who's winning it, and "The one move to flip it" (the content brief title + rationale). **Competitor Comparison table**: you vs each competitor with % and a Winning / You are ahead chip.

**Page 5 — The work.** **"Your competitors are winning here"**: a green "1 previously-lost question won back this period" banner, then the open lost-query table (question · who AI recommends · platform · status chip). **"Inaccurate AI answers flagged"**: hallucination table with fix status. **AI Readiness Toolkit**: llms.txt / schema.json / robots.txt each with a Verified chip.

**Page 6 — Next step.** One highlighted **Recommended Action** box, and the compliance footer: *"Manual dimension scores (Brand Authority, Content Quality) are assessed by the SeenBy team."*

The **report email** to the client attaches the PDF and links the share view.

---

# Part 5 — The Client Side (`/view/<256-bit-token>`)

No login. Whitelisted schemas only — raw AI responses, confidence scores, and internals can never leak here. Header: SeenBy wordmark, client name, domain, industry, optional logo; five tabs.

## 5.1 Overview

- **Score hero**: ring, 60/100, **"Your AI Visibility Score — Fair"**, *"You're seen by AI in 32 of 71 buyer questions"*, last-updated + **"Next visibility check due 22 Jul"** (freshness reassurance driven by the cadence setting), and a trust chip: *"1 item we fixed this month."*
- **Straight From AI Search** — verbatim quote cards: what ChatGPT/Perplexity said about you (Seen by AI, green) and an **Opportunity** card where a competitor was recommended instead — with the competitor's name masked as "[a competitor]" (we don't advertise rivals on the client's own page).
- **What AI Visibility Is Worth** — *"RM 16,128 estimated pipeline this month — ≈ 1,680 visitors arrived from AI search → about 34 leads → RM 3,226 in estimated won business."* The CEO line (§2.8 math).
- **Seen by AI — by Platform** — the four % cards.
- **Score Breakdown** — five expandable rows (labeled **"AI Visibility"** instead of "AI Citability" — friendlier), manual dimensions carrying the evidence label.
- **What We're Working On** — the diagnosed weaknesses in plain words + the prioritized action list (high/low chips).
- **What We're Fixing** — the remediation list with Flagged / In progress / Corrected chips and a "1 resolved" counter. This section is the retainer's heartbeat: the client watches items move.
- **Your score over time** + **AI visitors over time** — two bar charts (55→60; 1,320→1,680).
- Footer: "Powered by SeenBy — AI visibility tracking" (also my viral loop — every client view advertises us).

## 5.2 Scan & Visibility

"Seen by AI in 32 of 71 questions — We asked AI platforms the questions your customers ask." Four sections mirroring the categories with client-friendly names: **Questions about your brand**, **You vs competitors**, **Local search questions**, **Best-in-industry questions**. Every row: platform icon, the question, Seen/Not-seen chip, and on Seen rows an expandable **"See what AI said"** excerpt. Full transparency without raw dumps.

## 5.3 Competitors

Their 44% with per-platform chips; the same multi-line **visibility-over-time chart** as the admin side; a plain-language callout ("Sentosa Healthcare, Care Clinic Group are currently seen by AI more often than you"); then per-competitor cards with a one-line diagnosis ("Seen by AI on 11 of 16 questions and ahead of you on ChatGPT, Perplexity, Gemini, Claude — strongest on brand-name questions") and the query-by-query list.

## 5.4 Content Plan

**Where Your Content Stands** — topic coverage with Strong / Needs work / Missing chips, "Key details AI looks for" (entity checklist ✓/○), and "Our recommendation." Then **Your 90-Day Content Plan** — the weekly cards, each with priority, rationale, clickable full draft, and *"Wins back these questions"* listing the exact lost queries the piece targets. The client sees a plan, not a report card.

## 5.5 Reports

Delivered monthly PDFs (only after I hit send). Currently: "No reports yet — your first monthly visibility report will appear here once it's been delivered by the SeenBy team."

---

# Part 6 — The Skeptic's Audit

*Founder hat off. I'm now a skeptical investor / an acquiring agency's head of product doing diligence, having just watched the demo above. Here is everything unsatisfactory, ranked roughly by how much it threatens the RM4,000/month price point and an acquisition story.*

## 6.1 Things that would embarrass you in a client meeting (fix first)

1. **The proof quotes are garbage.** The single most emotional feature — "What AI said about you" — renders as `"Medilink Healthcare"`, `"Medilink Healthcare 2."` and `"[a competitor] 2."` on the client view AND in the monthly PDF (page 2). That's a snippet-extraction bug or unusably lax quality gate. A client paying RM4,000/month opens their report and the "evidence" is a two-word fragment with a stray list number. This actively *destroys* trust in every other number. Proof cards need a minimum-quality gate (full sentence, contains a verb, length threshold) and should be suppressed entirely when nothing passes.
2. **32 of 72 vs 32 of 71.** The admin panel, scorecard PDF, and monthly report say 72 tracked queries; the client view hero and scan tab say **71**. One discrepancy like this in diligence and every metric in the product becomes suspect. Find the off-by-one (likely a whitelist filter dropping one result) and add a consistency test.
3. **The monthly report's period is wrong.** The report is titled "July 2026" and claims "seen by AI in 32 of 72 tracked queries **during July 2026**" — but the scan ran 22 June. It's labeled by generation date, not data period. An observant client will call this out immediately.
4. **PDF cover header is broken.** The page header wordmark renders clipped as "SeenI" on every page, and page 1 has a duplicated header block colliding with the cover art. For a "consulting-grade" deliverable, the first pixel a client sees is a rendering bug.
5. **"Tracking begins soon — We're connecting your analytics"** (report p.4) is a lie on two counts: nothing is being connected (it's manual monthly entry), and June's number (1,680) *exists* — the report just looks at the wrong month. Either pull the latest available month with a date label, or say honestly "reported from your analytics by the SeenBy team."
6. **Report generation fails silently.** I clicked Generate Report, the UI promised "updates automatically in 30–60 seconds," and it just quietly returned to "No reports yet" because the Celery worker wasn't running. No error, no retry indicator, no worker-health surface anywhere in the admin. As the only operator, you need to *know* when your pipeline is dead — a failed-job banner at minimum.
7. **Dead section in the demo:** "Sources AI trusts in your category" shows "No source data yet. Run a scan." Your flagship differentiator (Share-of-Source) is invisible in the exact demo you'd show a buyer. Backfill or re-scan the demo client before any pitch.
8. **Roadmap says "12 weekly content pieces," shows 3.** Either generate 12 or make the copy reflect reality ("first 3 of 12"). Overpromise-underdeliver in the very artifact that sells the retainer.

## 6.2 Methodology gaps a sophisticated buyer will poke at

9. **Single-shot queries = noise presented as signal.** AI answers are stochastic; the same question re-asked can flip Seen↔Not-seen. You run each query once per scan, then present "+14.5 pts visibility" and "21 newly seen" as achievement. Some of that delta is dice rolls. Competitors in this space run repeated samples and show stability. At minimum: run each query 2–3× and report the majority; or track rolling averages; or show the admin (not the client) a variance estimate. Right now the product cannot distinguish your content work from randomness — which is an existential question for a results-based retainer.
10. **"Seen by AI" is a substring match, not an endorsement.** The regex counts *"I'd avoid Medilink Healthcare — their reviews are poor"* as **Seen by AI**. No sentiment or context classification. One sarcastic answer counted as a "win" in a client-facing table is a lawsuit-grade embarrassment for a healthcare client. You already call Claude for position extraction; a sentiment/polarity check on the same call is nearly free.
11. **20 points of the GEO score are a binary switch.** Technical Foundations + Structured Data go 0→100 by uploading three files — inflating Medilink from "would be 40 (Developing)" to "60 (Fair)" while actual AI visibility is 44%. It also means every client jumps ~20 points in week one (great for the "improvement" narrative, but it's self-graded easy credit) and the score can never move there again. Consider granular checks (file exists / valid / rich / fresh) worth partial credit.
12. **Contradiction on the same client: Content Gaps says "Structured data: None" while the Structured Data dimension is 100/100.** Explainable (on-page crawl vs hosted schema.json verification) but it *looks* like the product disagrees with itself. Reconcile or annotate.
13. **The agency grades its own homework.** Brand Authority (58) and Content Quality (55) are 40% of the score, set by the person selling the fix. The evidence label helps, but a skeptical CMO will ask: "so when you do the work, you also decide whether the number goes up?" You need external anchoring — the industry benchmark service exists (min 3 peers); surface it next to manual scores, and consider locking score *increases* to documented evidence entries.
14. **Asymmetric sample sizes in the head-to-head.** The client is measured on ~10 neutral queries per platform, competitors on 2 (their 16 tracking queries span 4 categories × 4 platforms). "Sentosa: 69% visibility" is built on far fewer, differently-worded queries than yours — yet the Gap Matrix and PDF competitor table present them as directly comparable. Either equalize the neutral-query sets or footnote the basis.
15. **Claude judges Claude.** Position extraction and content assessment use Claude — including for answers *produced by* Claude-the-platform. Cheap objection, easy PR hit ("AI grading its own answers"). Worth a line of methodology documentation, at minimum.
16. **Static query templates.** Every Malaysian healthcare client gets nearly identical queries with the industry string substituted in. "Health-screening questions are a high-volume AI query type" is asserted with zero volume data behind it. There's no per-client query customization visible in the UI (the checklist says "customize seed queries" but there's no screen for it). Real buyer questions differ per business; this is the ceiling on how "bespoke" the retainer can claim to be.

## 6.3 Product & UX weaknesses

17. **The client's "What We're Fixing" list is a wall of 20 red "Flagged" chips and one "Corrected."** No dates, no owner, no expected resolution. It reads like an untouched backlog, not an active service. Cap the visible list to the top items, group duplicates (the same query lost on 3 platforms shows as 3 rows), and show "flagged on / last checked" dates.
18. **Remediation duplicates the query dimension.** "Where can I find primary care…" appears once per platform in remediation — the client-relevant unit is the *question*, with platforms as chips on one row.
19. **The pipeline widget mixes tracked and assumed numbers with one tiny "estimated."** "≈ 1,680 visitors arrived from AI search" — that's a manually keyed number, and 2%/20% are defaults I never validated with the client. RM16,128 will be quoted in their board meeting. When it's challenged, the whole product's credibility goes with it. Show the assumptions inline ("based on your RM480 avg deal, 2% and 20% — adjust with us") and label the visitor count's source.
20. **Recommendation on PDF page 6 is a canned tip** ("verify your llms.txt is live") for a client whose llms.txt is *verified on page 5 of the same report*. The static band-tip fallback is fine for the weekly digest; in the flagship monthly document it must be the top Action Center item instead.
21. **Naming drift for the same metric:** "AI Citability" (admin + PDF breakdown), "AI Visibility" (client view breakdown), and the PDF competitor table header "AI CITABILITY" — where the number shown is actually *visibility frequency*, not the citability dimension. Also "citability" flirts with your own banned-language table on a client-facing surface. Pick one client-facing name; keep "citability" internal.
22. **Scorecard platform "Status" column is dead weight** — all four rows say "Seen by AI" whether 39% or 50%. Replace with trend arrows or band words.
23. **Test data pollutes the production dashboard** ("ZZ Test Prospect DELETE", "ZZ Test Prospect TWO DELETE" stuck in "Scanning…"). Also evidence that stuck scans linger in a fake in-progress state — the 15-min stale-scan rule apparently doesn't update the card label.
24. **The Checklist page isn't in the documented nav** (CLAUDE.md §9 has no /checklist route) — doc drift; and its "browser-only" persistence means your onboarding progress evaporates if you switch machines. Fine for one operator today; a blocker the day you hire.
25. **Client view has no methodology page.** The client sees percentages, an RM figure, and a score with no "how we measure" link. For a skeptical stakeholder, a one-screen "72 questions monthly across 4 AI platforms, here's how scoring works" page converts doubt into trust — and it's nearly free to build.
26. **Share links never expire.** 256-bit token, revocable, uniform 404 — good. But links live forever by default, get forwarded, and end up in inboxes of people who left the company. Offer optional expiry/rotation reminders.

## 6.4 Business-level risks (the RM4,000 and acquisition questions)

27. **The visible monthly deliverable is thin against the price.** One 72-query scan, a PDF, a digest, ~3 content briefs. Global tools (Profound, Peec, Otterly) do daily scans of hundreds of prompts at USD 99–500/month self-serve. Your defense is the *service layer* (human review, remediation, written articles, local-market focus) — but the product itself should make that labor visible. The Activity Log has it; the client never sees it. A "what your team did this month" section in the report (X briefs written, Y items remediated, Z hours) directly defends the retainer.
28. **On-demand-only scanning caps growth.** Everything routes through your hands: scans, manual scores, traffic entry, report review, sending. That's the model — but at 20 clients it's your whole month, and an acquirer buying "a platform" will discount hard if it's really "Faris plus scripts." The scheduled-scan prohibition is an MVP scope rule, not a strategy; the roadmap to operator-leverage (scheduled scans + review queues) should exist on paper even if unbuilt.
29. **Single-admin, no multi-tenancy, no white-label is the #1 acquisition blocker.** A marketing agency acquirer wants to run *their* clients under *their* brand with *their* team. All three are explicitly out of MVP scope — fine — but the acquisition thesis in this walkthrough depends on them, so the architecture should not paint itself into a corner (e.g., the hardcoded single API key, contact@seenby.my literals, single-operator assumptions in copy).
30. **The moat is the longitudinal data — and it's underexploited.** Nobody can retroactively reconstruct what ChatGPT said about a Malaysian clinic in May 2026. You have it, timestamped and raw (for 90 days — then purged!). Consider retaining *derived* history indefinitely and even anonymized cross-client industry trends ("AI visibility in Malaysian healthcare, Q3 2026") as marketing and as the dataset an acquirer actually pays for. Purging raw responses at 90 days is privacy-sound; make sure everything worth keeping is extracted first.
31. **Unit economics are invisible in the UI.** A cost tracker exists in the backend (`cost_tracker.py` records every LLM call), and there are per-scan budget caps — but no admin screen shows cost-per-scan or margin per client. For pricing decisions and diligence, surface it.
32. **No churn story.** When a client's score stalls at "Fair" for four months (Sentosa is a bigger operation and may simply keep winning), what does the report say? The current design always finds positives ("1 question won back"), but there's no honest mechanism for "the ceiling for your brand size is ~55 and here's why" — and an unmanaged expectations gap is how retainers die. Consider an explicit target-setting feature (agree a 90-day score target with the client, track against it).

## 6.5 What I'd remove or hide

- **Junk proof quotes** (until quality-gated) — worse than nothing.
- **"Tracking begins soon"** copy — replace with honest sourcing.
- **Empty Share-of-Source section** on clients with no source data — hide until populated.
- **The scorecard's constant "Seen by AI" status column.**
- **Test prospects** from the production database.
- **Duplicate remediation rows** (collapse per-question).

## 6.6 The bottom line (skeptic's verdict)

The bones are genuinely good: a coherent scoring model with the human accountable for the subjective 40%, evidence-first client UX in disciplined language, a real remediation loop that proves work, a provenance feature pointing at true differentiation, and unusually thoughtful engineering hygiene for a solo build (platform-failure isolation, cost caps, retention policy, banned-language enforcement, signed URLs, uniform 404s).

But today, the demo contains **five self-contradicting or broken numbers/artifacts** (§6.1: quotes, 71/72, period label, header render, traffic claim) — and for a product whose entire value proposition is *"trust our measurement"*, measurement bugs are not cosmetic; they are the product. Fix the §6.1 list this week; address noise/sentiment (§6.2 items 9–10) before the next client pitch; and put the operator-leverage + white-label roadmap on paper for the acquisition story. Then RM4,000/month is defensible — because what's actually being sold isn't the scan, it's the accountable human loop around it, and the product finally proves that loop everywhere the client looks.

---

*Appendix — artifacts generated during this walkthrough (in the project root): `scorecard-medilink.pdf`, `monthly-report-medilink.pdf` (rendered locally through the real report pipeline, no R2 upload), page snapshots `snap-*.yml`, and screenshots `01-clients-overview.jpeg`, `02-medilink-overview.jpeg`, `03-share-snippet.jpeg`.*
