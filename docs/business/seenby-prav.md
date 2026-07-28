# SeenBy — Company & Product Overview (Updated)

*A plain-English walkthrough of what SeenBy is, why it exists, and how the platform works — written for investors, stakeholders, and partners.*

---

## 1. What is SeenBy?

SeenBy is a service that tells businesses **whether AI chatbots like ChatGPT, Gemini, Claude, and Perplexity actually talk about them** — and helps them get mentioned more often.

For the last 20 years, businesses cared about Google rankings ("SEO"). Today, more and more people don't Google things — they ask ChatGPT, Gemini, or Perplexity directly:

> "What's the best digital marketing agency in Kuala Lumpur?"
> "Compare [Brand A] vs [Brand B]"
> "Recommend a good [service] near me"

If an AI never mentions a business in answers like these, that business is **invisible** to a growing slice of its potential customers — and the business owner has no way of knowing it's happening. SeenBy makes that invisible problem visible, measurable, and fixable.

This category is called **GEO** — Generative Engine Optimization. It's the AI-era equivalent of SEO, and it's still early — most businesses (and most agencies) don't have tools for it yet.

A pure score-and-report product only answers "are we visible?" — but the client who actually renews a monthly retainer (the reference persona is a Malaysian SME clinic owner) doesn't buy a visibility score. They buy patients, and not losing them to a named rival. So beyond measuring visibility, SeenBy now goes a layer further at every touchpoint: it shows the client the actual AI conversation, puts a ringgit figure on what it's worth, and names the specific competitor currently winning it. That thread runs through most of what's described below.

---

## 2. Who is SeenBy for?

SeenBy runs on an **agency model**. There is one admin (the SeenBy team) who manages everything on behalf of clients — clients don't log into a dashboard or manage anything themselves. This keeps the product simple and lets SeenBy package it as a managed service (similar to how a marketing agency manages SEO or ads for a client).

Two types of businesses are tracked in the system:

- **Clients** — paying customers. They get regular scans, reports, and a private read-only link to view their results.
- **Prospects** — businesses SeenBy hasn't signed yet. The admin can run a scan on a prospect *before* they're a customer, to show them (in a sales pitch) exactly how invisible — or visible — they currently are to AI. If they sign up, the prospect is converted into a client with one click, and all their existing scan history carries over.

---

## 3. The core idea: "Seen by AI" or "Not seen by AI"

Everything in the product boils down to one simple, non-technical idea per business:

- **Seen by AI** — when someone asks an AI chatbot a relevant question, the AI mentions this business.
- **Not seen by AI** — the AI answers the question but doesn't mention this business (often a competitor gets mentioned instead).

SeenBy deliberately avoids technical/SEO jargon like "citation rate" or "ranking position" in anything a client sees. Everything is phrased as "Seen by AI," "Not yet seen by AI," "Your AI Search Ranking," or "Your competitors are winning here." The goal is that a non-technical business owner opens a report and immediately understands their situation — no explanation needed.

Increasingly, that idea isn't left as an abstract label — the client can now read the actual AI answer that produced it. SeenBy stores the full verbatim response from every scan query, and surfaces it directly as a proof card: "A buyer asked ChatGPT 'best dental clinic in KL' — here's the actual answer, and you're named in paragraph one" for a win, or the actual answer where a competitor got named instead, framed as the opportunity to flip. These cards are the hero proof on the client's read-only overview page, an inline expandable on every scan result, the quote in the weekly digest email, and a full section in the monthly PDF. A deliberate rule governs how far a rival's name travels with the quote: it's **redacted to "[a competitor]" on every public or shareable surface** (anything that could be forwarded outside the relationship) but **named outright on private, inbox-delivered surfaces** — the weekly digest and the monthly PDF — where naming the rival is exactly what drives renewal.

---

## 4. How a scan works (the engine room)

This is the heart of the product. When the admin clicks "Run Scan" for a client:

1. **SeenBy asks real AI chatbots real questions** — the same kinds of questions a potential customer would ask. Up to **20 questions per AI platform** (5 per category × 4 categories):
   - **Brand** — "Tell me about [Brand]", "What is [Brand] known for?"
   - **Comparison** — "[Brand] vs [Competitor]" (capped by how many competitors the client has — up to 5, so a client with no competitors on file simply runs 15 queries instead of 20)
   - **Recommendation** — "Best [industry] in [location]"
   - **Local** — "Best [industry] near me in [city]"

2. **This happens across 4 major AI platforms**: ChatGPT, Perplexity, Gemini, and Claude. Each client can choose which platforms to scan (at least one), so costs can be tuned per client.

3. **SeenBy reads every AI response** and checks: did the AI mention this business by name? Did it mention any competitors instead?

4. **If a platform fails**, SeenBy retries once. If it still fails, the scan continues anyway using the platforms that worked — the score is computed from the remaining platforms, the failed one is marked unavailable, and the failure is logged. Nothing blocks the client from getting their results.

5. **Raw AI responses are stored for 90 days** (for audit/review, and to power the verbatim answer cards above), then automatically deleted to control storage costs and keep data tidy.

The output of a scan is the raw evidence behind everything else in the product — the score, the win/loss board, the money estimates, the competitive narrative, the content recommendations, all trace back to these real AI conversations.

---

## 5. The GEO Score — one number that explains everything

Every client gets a single overall score from **0–100**, color-coded like a traffic light:

| Score | Meaning | Color |
|---|---|---|
| 70–100 | Strong AI visibility | 🟢 Green |
| 30–69 | Mixed / needs work | 🟡 Yellow |
| 0–29 | Largely invisible to AI | 🔴 Red |

The score is made of 5 ingredients:

| What it measures | How much it counts | Where it comes from |
|---|---|---|
| **AI Citability** — how often AI actually mentions the brand | 40% | Automatic, from the scan |
| **Brand Authority** — overall reputation/authority signals | 20% | **Assisted** — Claude drafts a suggested score with evidence, admin reviews and gates it |
| **Content Quality** — quality of the brand's website/content | 20% | **Assisted** — Claude drafts a suggested score with evidence, admin reviews and gates it |
| **Technical Foundations** — is the site set up so AI crawlers can read it? | 10% | Automatic, verified by the toolkit (see below) |
| **Structured Data** — does the site describe itself in a machine-readable way? | 10% | Automatic, verified by the toolkit (see below) |

Brand Authority and Content Quality used to be bare admin judgment calls, labeled "Assessed by SeenBy team" with no visible reasoning behind them. Because SeenBy both sells the service *and* assigns 40% of the score that measures the service's value, that was a real credibility gap — a sophisticated client could reasonably suspect the number was inflated to justify the retainer. The fix: on an admin-triggered "Generate assessment" action, Claude now produces a suggested score plus 3–5 concise, plain-English evidence bullets per dimension, grounded in the client's public web presence. The admin reviews, can accept or adjust the number, and only the accepted number ever counts toward the score. The evidence bullets are shown to the client, always labeled **"Based on public evidence · Reviewed by SeenBy."** This is assisted, human-reviewed scoring, not full automation — the admin remains the gate on every number that reaches a client, which preserves the human-expert premium that justifies the retainer while removing the "just trust us" feel of the old version.

Before a client's first scan, the score simply shows "Awaiting first scan" rather than a misleading 0.

Alongside the score, every client with revenue inputs on file (average deal value, visitor-to-lead and lead-to-close rates) also gets a companion money story, told as a pair: **captured value** — how much real pipeline came from AI-referral traffic the client actually received this period — and **value at risk** — a conservative, gap-scaled estimate of what invisibility is still costing. The at-risk number reuses the exact same conversion chain as the captured number (same deal value, same rates) scaled by how much of the client's visibility gap remains unclosed, floored so a near-zero score can't produce an absurd multiplier and hard-capped so at-risk is **never shown as more than 3× captured** — a business that hasn't earned the "captured" number shouldn't see a runaway "at risk" number either. It's hidden entirely for any client who hasn't configured revenue inputs, so no figure is ever shown that isn't grounded in the client's own numbers. This pairing appears on the client overview, the weekly digest, and a dedicated section in the monthly PDF.

---

## 6. What the admin sees (the control room)

The SeenBy team manages everything from one admin panel. Here's what each section does, in plain terms:

### All Clients (`/clients`)
A list of every client, each shown as a card with their name, current score, color band, and when they were last scanned. One glance tells the admin who needs attention.

### Competitor Gap Matrix (`/clients/gap-matrix`)
A portfolio-wide view, not a per-client one: recommendation and local visibility across **every active client at once**, computed from each client's latest completed scan. Where the per-client competitor page answers "how is this one client doing against their rivals," the gap matrix answers "across my whole book of business, where are the recurring visibility gaps" — useful for spotting patterns and prioritizing which clients need attention first.

### Client Overview (`/clients/[id]`)
The home page for one client: their current score, how it's trending over time, the captured/at-risk money pairing described above, and an **Action Center** — a short list of 3–5 specific, prioritized things to do next to improve their score (e.g., "Fix X and your score could rise by roughly Y points"). These suggestions are AI-generated but the impact numbers are calculated by SeenBy's own formulas, not just trusted blindly from the AI — so they stay realistic and consistent.

### Scan & Visibility (`/clients/[id]/scan`)
Where the admin triggers a new scan and reviews results — which questions were asked, which AI platform answered, whether the brand was mentioned, and the actual AI response text (for internal review only — never shown to clients in unredacted form).

A **"Flag hallucination"** button lets the admin mark any AI response that says something false or misleading about the client. This creates a record and sends an internal alert — useful for catching AI misinformation about a client's business early.

### Competitor Intelligence (`/clients/[id]/competitors`)
Side-by-side comparison: how often is *this* client mentioned by AI vs. up to 5 of their competitors? Includes a **"Win/Loss" board** — for each type of question, did the client "win" (AI mentioned them), "lose" (AI mentioned a competitor instead), or is it "open" (neither mentioned)? This instantly shows where competitors are beating the client in AI conversations, and rivals are named outright here since it's an admin/authenticated surface.

That win/loss data now also drives a sharper, single-sentence version of the same story: a deterministic (no AI call involved) selector looks across every query the client is currently losing, finds the one rival showing up most often, and picks the single highest-priority lost query against that rival — recommendation and local queries outrank brand and comparison ones, since they're closest to a real buying moment. It's paired with the "one move" to fix it, reusing the content brief already written for that exact query (see the content roadmap below), so the two never tell inconsistent stories. The result reads as: *"[Named competitor] is winning [specific query] — here's the one move to flip it."* It shows up in the weekly digest and as its own section in the monthly PDF.

If a competitor's visibility score overtakes the client's, an automatic alert goes out (see the reliability section below).

### Content Gaps (`/clients/[id]/content-gaps`)
SeenBy crawls the client's actual website and uses AI to analyze: what topics and questions does their content already cover well, and what's missing? This is informational — it never changes the score automatically — but it tells the admin (and eventually the client) where the content has holes.

### 90-Day Content Roadmap (`/clients/[id]/content-roadmap`)
This takes the "lost" and "open" questions from the Win/Loss board — i.e., the exact questions where AI currently recommends competitors instead of this client — and turns them into a **12-week content plan**, one article topic per week, each with a drafted content brief. The logic: if AI doesn't see content from this brand answering a question, write that content. The same brief also powers the "one move" in the competitor narrative above, so the roadmap and the rivalry story are always consistent with each other.

### AI Readiness Toolkit (`/clients/[id]/toolkit`)
Three technical files that help AI crawlers understand and access a website properly:
- **llms.txt** — a short, AI-readable summary of the business (a new emerging web standard)
- **schema.json** — structured data describing the business, used by AI/search systems
- **robots.txt** — explicitly allows AI crawlers (GPTBot, PerplexityBot, ClaudeBot, Google-Extended, etc.) to access the site

All three are auto-generated by AI from the client's info, with copy/download buttons and plain-English setup instructions (so even a non-technical client could hand them to a web developer). Once the client adds these files to their site, SeenBy can **verify** they're live with one click — and verified files automatically boost the "Technical Foundations" and "Structured Data" parts of the score.

### Onboarding Checklist (`/clients/[id]/checklist`)
A simple, editable to-do list per client covering the setup steps needed to fully onboard them. Helps the admin make sure nothing falls through the cracks when bringing on a new client.

### Reports (`/clients/[id]/reports`)
- **Weekly email digest** — automatically sent every Monday if a scan ran that week. Shows the current score, the trend (up/down/flat), how many times AI "saw" the brand that week, the captured/at-risk money headline, the named competitor battle for the week, and either a custom AI-written tip (if the score moved meaningfully) or a standard tip.
- **Monthly PDF report** — see the dedicated section below. Reviewed by the SeenBy team before it's sent.

### Activity Log (`/clients/[id]/activity`)
A running history of everything that's happened for this client — scans completed, score changes, alerts, reports sent, manual notes. Acts as an audit trail and a quick "what's the story with this client" view.

### Settings (`/clients/[id]/settings`)
Where the admin manages client details, which AI platforms to scan, the score-drop alert threshold, revenue inputs (average deal value, conversion rates — required to unlock the money story above), and the **client view share link** (see below).

### Industry Benchmarking
Clients can (optionally) see how their score compares to other SeenBy clients in the same industry — shown only as an anonymous percentile/ranking, never naming other businesses, and only shown once there's a large enough group to keep it anonymous.

### AI Referral Traffic (manual entry)
The admin can record how many visitors a client's website got *from AI platforms* each month (from the client's own analytics). This directly powers the captured-value and at-risk-value calculations above, not just narrative context.

---

## 7. What the client sees (the read-only view)

Clients don't have logins or passwords. Instead, each client gets a **private link** (a long, unguessable URL) that the admin can share with them. Anyone with that link can view (read-only):

- `/view/[link]` — Their overall score, the 5-dimension breakdown (with evidence bullets for the two assisted dimensions), captured/at-risk revenue if configured, AI referral traffic if recorded, score history over time, and the hero verbatim answer cards
- `/view/[link]/scan` — Their "Seen by AI" / "Not seen by AI" breakdown per platform and per question type, with inline expandable verbatim answer cards per result
- `/view/[link]/competitors` — How they compare to their competitors in AI visibility, including the named-rival battle
- `/view/[link]/content-plan` — Their 90-day content roadmap
- `/view/[link]/reports` — Their delivered monthly PDF reports

Because this link is shareable outside the direct relationship, competitor names are redacted to "[a competitor]" everywhere on it — never named — even though the same underlying story is named outright in the client's private inbox (digest and PDF). If a link is invalid, revoked, or the client has been archived, the page simply shows a generic "not found" — so no information leaks about whether a link ever existed. Internal-only information (raw unredacted AI response text, confidence scores, technical scan details) is never exposed on this side, by design.

---

## 8. The monthly PDF report — consulting-grade redesign

The monthly PDF was rebuilt from a functional HTML-to-PDF document into a premium, consulting-grade deliverable — styled after the kind of report a McKinsey or Deloitte engagement would produce, on the theory that a client paying a monthly retainer should receive something that *looks* earned. Key changes:

- A full-bleed dark cover page (ink navy) with the client's score as a large gauge, and the AI-written "what changed this month" narrative moved onto the cover itself rather than buried mid-document — so the first thing a client sees on opening the PDF is the headline story, not a table of contents.
- A restrained color system — a single confident blue accent used only for section headers, the recommended-action box, and the score gauge, so its appearance always signals something rather than decorating everything.
- A running dark header and footer with page numbers on every page after the cover.
- The section order was re-sequenced for narrative flow rather than data-logic grouping: **AI Visibility Score → What AI Said About You (the verbatim proof cards) → Score Breakdown → AI Visibility Frequency & Platform Breakdown → AI Referral Traffic → Estimated Pipeline Still On The Table (the at-risk money) → The Battle To Win Next (the named rival and the one move) → Competitor Comparison → Content Gaps → Flagged Inaccurate AI Answers → AI Readiness Toolkit → Recommended Action.** The intent is an emotional arc — proof, then money, then rivalry, then the supporting detail — rather than a flat data dump.
- Every AI-written narrative element on the PDF (the cover summary, the recommended action) is generated once at report build time and persisted on the report record, so re-opening or re-sending a report always shows the same text rather than regenerating it.

The admin still reviews every PDF before it goes out — this redesign changes the presentation, not the human-in-the-loop gate.

---

## 9. The "prospect" workflow — SeenBy's own sales tool

One of the more powerful business uses of the platform is for SeenBy's *own* sales process:

1. Before pitching a potential client, the admin adds them to SeenBy as a **prospect** and runs a real scan on them — for free, using SeenBy's own scanning capability.
2. The admin now has hard evidence: "Here's exactly what happens when someone asks ChatGPT about your business right now — and here's what your competitor gets instead, named outright, with the exact answer text and a ringgit figure attached."
3. Prospects are kept separate from the main client list so they don't clutter the portfolio view.
4. If the prospect signs up, the admin flips one switch ("Convert to Client") — their scan history, score, and everything else carries forward seamlessly. No data is lost, no re-onboarding needed.

This turns the product itself into a cold-outreach and sales-demo tool — a tangible, personalized "here's your problem, here's who's beating you, here's what it's costing you" before any sales conversation about the solution.

---

## 10. Behind the scenes — keeping it reliable and trustworthy

A few principles run through the whole platform, worth highlighting for anyone evaluating it:

- **Evidence-based, not guesswork** — every score, money figure, and competitive narrative traces back to real AI conversations that actually happened, not estimates or a separate speculative model.
- **Honest about what's automatic vs. assisted vs. manual** — AI Citability, Technical Foundations, and Structured Data are automatic; Brand Authority and Content Quality are Claude-suggested and human-reviewed, always labeled "Based on public evidence · Reviewed by SeenBy." Clients always know the difference between "the system measured this" and "our team reviewed and approved this."
- **AI suggestions are checked, not blindly trusted** — when Claude generates recommendations, dimension scores, or impact estimates, SeenBy's own formulas and admin review double-check and bound the numbers before showing them, so reports stay internally consistent and conservative (e.g., the at-risk money figure is hard-capped at 3× captured value).
- **Deterministic where it matters** — the named-rival competitive narrative runs with zero LLM calls in the automated flow; it reuses existing data and an already-approved content brief, so there's no risk of an automated system inventing a rivalry story on the fly.
- **Privacy-conscious by default** — client view links use long random tokens, invalid/revoked links look identical to non-existent ones, competitor names and raw unredacted responses never reach the public client-facing side, and old raw scan data is automatically purged after 90 days.
- **Resilient scanning** — if one AI platform is down or errors out, the scan still completes using the others; nothing blocks on a single point of failure.
- **Cost-aware** — each client can be scanned on a subset of AI platforms, and comparison queries scale down automatically for clients with fewer competitors on file, so cost scales sensibly with what a client actually needs tracked.
- **Alerts never block a scan** — score-drop, competitor-overtake, and hallucination alerts are sent best-effort, synchronously, from inside the scan flow. They always go to email, and now also push to Telegram for instant notification when configured — but a failed notification never undoes or blocks a completed scan.

---

## 11. The technology (brief, for context)

| Layer | What's used |
|---|---|
| Website / Admin panel | Next.js (modern web framework) |
| Backend / API | FastAPI (Python) |
| Database | PostgreSQL |
| Background jobs (scans, emails, reports) | Celery + Redis |
| AI providers | OpenAI (ChatGPT), Perplexity, Google (Gemini), Anthropic (Claude) |
| Email | Resend |
| Instant alerts | Telegram (in addition to email, best-effort) |
| PDF reports | WeasyPrint |
| File storage (PDFs etc.) | Cloudflare R2 |
| Hosting | Vercel (frontend), Railway (backend/workers) |

---

## 12. Where this is headed

The current build is intentionally lean — one admin runs everything, all scans are on-demand, and clients interact only through email and a read-only link. Deliberately **not** built yet (by design, to keep the MVP focused): client logins, self-serve signup/billing, white-labeling for other agencies, scheduled/automatic scans, webhook integrations, and full automation of Brand Authority/Content Quality scoring (these stay assisted and human-gated by design, not just for now).

The nearer-term roadmap has two parts. First, moving the AI Readiness Toolkit from "here are the files and instructions to implement yourself" to SeenBy implementing the fix directly for the client — closing the loop from "here's what to do" to "it's already done." Second, extending the story one layer further back: not just "AI doesn't mention you," but *why* — surfacing the reviews, directory listings, and third-party signals that make AI trust a competitor more, and turning that into an ongoing reputation-building loop rather than a one-time fix.

Beyond that, the same natural next steps from the original MVP still apply once the core product is validated with real clients: self-serve signup/billing, white-labeling for other agencies, and scheduled/automatic scans — each a clear path to scaling from "one agency managing this by hand" to "a self-serve platform other agencies or businesses could use directly."
