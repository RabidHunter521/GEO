# SeenBy — Company & Product Overview

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

---

## 4. How a scan works (the engine room)

This is the heart of the product. When the admin clicks "Run Scan" for a client:

1. **SeenBy asks real AI chatbots real questions** — the same kinds of questions a potential customer would ask. Up to **20 different questions per AI platform**, across 4 categories:
   - **Brand** — "Tell me about [Brand]", "What is [Brand] known for?"
   - **Comparison** — "[Brand] vs [Competitor]"
   - **Recommendation** — "Best [industry] in [location]"
   - **Local** — "Best [industry] near me in [city]"

2. **This happens across 4 major AI platforms**: ChatGPT, Perplexity, Gemini, and Claude. Each client can choose which platforms to scan (at least one), so costs can be tuned per client.

3. **SeenBy reads every AI response** and checks: did the AI mention this business by name? Did it mention any competitors instead?

4. **If a platform fails** (an API error, etc.), SeenBy retries once. If it still fails, the scan continues anyway using the platforms that worked — nothing blocks the client from getting their results, and the failure is logged.

5. **Raw AI responses are stored for 90 days** (for audit/review), then automatically deleted to control storage costs and keep data tidy.

The output of a scan is the raw evidence behind everything else in the product — the score, the competitor comparisons, the content recommendations, all trace back to these real AI conversations.

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
| **Brand Authority** — overall reputation/authority signals | 20% | SeenBy team's manual assessment |
| **Content Quality** — quality of the brand's website/content | 20% | SeenBy team's manual assessment |
| **Technical Foundations** — is the site set up so AI crawlers can read it? | 10% | Automatic, verified by the toolkit (see below) |
| **Structured Data** — does the site describe itself in a machine-readable way? | 10% | Automatic, verified by the toolkit (see below) |

Anything assessed manually by the SeenBy team is always labeled **"Assessed by SeenBy team"** so it's transparent to the client that a human reviewed it — not just a robot.

Before a client's first scan, the score simply shows "Awaiting first scan" rather than a misleading 0.

---

## 6. What the admin sees (the control room)

The SeenBy team manages everything from one admin panel. Here's what each section does, in plain terms:

### All Clients (`/clients`)
A list of every client, each shown as a card with their name, current score, color band, and when they were last scanned. One glance tells the admin who needs attention.

### Client Overview (`/clients/[id]`)
The home page for one client: their current score, how it's trending over time, and an **Action Center** — a short list of 3–5 specific, prioritized things to do next to improve their score (e.g., "Fix X and your score could rise by roughly Y points"). These suggestions are AI-generated but the impact numbers are calculated by SeenBy's own formulas, not just trusted blindly from the AI — so they stay realistic and consistent.

### Scan & Visibility (`/clients/[id]/scan`)
Where the admin triggers a new scan and reviews results — which questions were asked, which AI platform answered, whether the brand was mentioned, and the actual AI response text (for internal review only — never shown to clients).

A **"Flag hallucination"** button lets the admin mark any AI response that says something false or misleading about the client. This creates a record and sends an internal alert — useful for catching AI misinformation about a client's business early.

### Competitor Intelligence (`/clients/[id]/competitors`)
Side-by-side comparison: how often is *this* client mentioned by AI vs. up to 5 of their competitors? Includes a **"Win/Loss" board** — for each type of question, did the client "win" (AI mentioned them), "lose" (AI mentioned a competitor instead), or is it "open" (neither mentioned)? This instantly shows where competitors are beating the client in AI conversations.

If a competitor's visibility score overtakes the client's, an automatic alert email goes out to the SeenBy team.

### Content Gaps (`/clients/[id]/content-gaps`)
SeenBy crawls the client's actual website and uses AI to analyze: what topics and questions does their content already cover well, and what's missing? This is informational — it never changes the score automatically — but it tells the admin (and eventually the client) where the content has holes.

### 90-Day Content Roadmap (`/clients/[id]/content-roadmap`)
This takes the "lost" and "open" questions from the Win/Loss board — i.e., the exact questions where AI currently recommends competitors instead of this client — and turns them into a **12-week content plan**, one article topic per week, each with a drafted article. The logic: if AI doesn't see content from this brand answering a question, write that content. This is one of the most concrete, actionable deliverables in the product — a real content calendar generated from real evidence of what's being missed.

### AI Readiness Toolkit (`/clients/[id]/toolkit`)
Three technical files that help AI crawlers understand and access a website properly:
- **llms.txt** — a short, AI-readable summary of the business (a new emerging web standard)
- **schema.json** — structured data describing the business, used by AI/search systems
- **robots.txt** — explicitly allows AI crawlers (GPTBot, PerplexityBot, ClaudeBot, etc.) to access the site

All three are auto-generated by AI from the client's info, with copy/download buttons and plain-English setup instructions (so even a non-technical client could hand them to a web developer). Once the client adds these files to their site, SeenBy can **verify** they're live with one click — and verified files automatically boost the "Technical Foundations" and "Structured Data" parts of the score.

### Onboarding Checklist (`/clients/[id]/checklist`)
A simple, editable to-do list per client covering the setup steps needed to fully onboard them (e.g., confirm contact details, set up the toolkit files, share the client view link, etc.). Helps the admin make sure nothing falls through the cracks when bringing on a new client.

### Reports (`/clients/[id]/reports`)
- **Weekly email digest** — automatically sent every Monday if a scan ran that week. Shows the current score, the trend (up/down/flat), how many times AI "saw" the brand that week, and either a custom AI-written tip (if the score moved meaningfully) or a standard tip.
- **Monthly PDF report** — a polished, branded PDF generated automatically every 30 days, reviewed by the SeenBy team before it's sent, including the overall score, the 5-dimension breakdown, competitor comparisons, an AI-written "what changed this month" summary, and clear "what to do next" recommendations. The admin clicks "Send to client" when it's ready.

### Activity Log (`/clients/[id]/activity`)
A running history of everything that's happened for this client — scans completed, score changes, alerts, reports sent, manual notes. Acts as an audit trail and a quick "what's the story with this client" view.

### Settings (`/clients/[id]/settings`)
Where the admin manages client details, which AI platforms to scan, the score-drop alert threshold, and the **client view share link** (see below).

### Industry Benchmarking
Clients can (optionally) see how their score compares to other SeenBy clients in the same industry — shown only as an anonymous percentile/ranking, never naming other businesses, and only shown once there's a large enough group to keep it anonymous.

### AI Referral Traffic (manual entry)
The admin can record how many visitors a client's website got *from AI platforms* each month (from the client's own analytics). This is purely informational context — it doesn't affect the score — but it helps tell the story of real-world impact over time.

---

## 7. What the client sees (the read-only view)

Clients don't have logins or passwords. Instead, each client gets a **private link** (a long, unguessable URL) that the admin can share with them. Anyone with that link can view (read-only):

- `/view/[link]` — Their overall score, the 5-dimension breakdown, AI referral traffic if recorded, and score history over time
- `/view/[link]/scan` — Their "Seen by AI" / "Not seen by AI" breakdown per platform and per question type
- `/view/[link]/competitors` — How they compare to their competitors in AI visibility
- `/view/[link]/content-plan` — Their 90-day content roadmap
- `/view/[link]/reports` — Their delivered monthly PDF reports

If a link is invalid, revoked, or the client has been archived, the page simply shows a generic "not found" — so no information leaks about whether a link ever existed. Internal-only information (raw AI response text, confidence scores, technical scan details) is never exposed on this side, by design.

---

## 8. The "prospect" workflow — SeenBy's own sales tool

One of the more powerful business uses of the platform is for SeenBy's *own* sales process:

1. Before pitching a potential client, the admin adds them to SeenBy as a **prospect** and runs a real scan on them — for free, using SeenBy's own scanning capability.
2. The admin now has hard evidence: "Here's exactly what happens when someone asks ChatGPT about your business right now — and here's what your competitor gets instead."
3. Prospects are kept separate from the main client list so they don't clutter the portfolio view.
4. If the prospect signs up, the admin flips one switch ("Convert to Client") — their scan history, score, and everything else carries forward seamlessly. No data is lost, no re-onboarding needed.

This turns the product itself into a cold-outreach and sales-demo tool — a tangible, personalized "here's your problem" before any sales conversation about the solution.

---

## 9. Behind the scenes — keeping it reliable and trustworthy

A few principles run through the whole platform, worth highlighting for anyone evaluating it:

- **Evidence-based, not guesswork** — every score and recommendation traces back to real AI conversations that actually happened, not estimates.
- **Honest about what's automatic vs. manual** — anything assessed by a human is clearly labeled "Assessed by SeenBy team," so clients always know the difference between "the system measured this" and "our team judged this."
- **AI suggestions are checked, not blindly trusted** — when AI (e.g., Claude) generates recommendations or impact estimates, SeenBy's own formulas double-check and bound the numbers before showing them, so reports stay internally consistent.
- **Privacy-conscious by default** — client view links use long random tokens, invalid/revoked links look identical to non-existent ones, raw AI responses and internal scoring details never reach the client-facing side, and old raw data is automatically purged after 90 days.
- **Resilient scanning** — if one AI platform is down or errors out, the scan still completes using the others; nothing blocks on a single point of failure.
- **Cost-aware** — each client can be scanned on a subset of AI platforms, so the cost of running the service scales sensibly with how many platforms a client cares about.

---

## 10. The technology (brief, for context)

| Layer | What's used |
|---|---|
| Website / Admin panel | Next.js (modern web framework) |
| Backend / API | FastAPI (Python) |
| Database | PostgreSQL |
| Background jobs (scans, emails, reports) | Celery + Redis |
| AI providers | OpenAI (ChatGPT), Perplexity, Google (Gemini), Anthropic (Claude) |
| Email | Resend |
| PDF reports | WeasyPrint |
| File storage (PDFs etc.) | Cloudflare R2 |
| Hosting | Vercel (frontend), Railway (backend/workers) |

---

## 11. Where this is headed

The current build is intentionally lean — one admin runs everything, all scans are on-demand, and clients interact only through email and a read-only link. Deliberately **not** built yet (by design, to keep the MVP focused): client logins, self-serve signup/billing, white-labeling for other agencies, scheduled/automatic scans, and automated scoring of brand authority/content quality.

These are natural next steps once the core product is validated with real clients — each represents a clear path to scaling from "one agency managing this by hand" to "a self-serve platform other agencies or businesses could use directly."
