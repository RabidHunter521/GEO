# SeenBy MVP — Design Spec
*2026-05-28*

## Context

SeenBy is an agency-model AI visibility tracking platform. Faris (sole admin) manages all clients, triggers scans manually, and sends reports. Clients have no login — they receive reports via email only. This spec covers the full MVP, agreed and locked before build begins.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Frontend | Next.js 15 + Tailwind + shadcn/ui → Vercel |
| Backend | FastAPI + SQLAlchemy → Railway |
| Jobs | Celery + Redis + Beat → Railway |
| Database | Supabase (PostgreSQL, free tier) |
| Storage | Supabase Storage (PDF reports) |
| Email | Resend + React Email |
| PDF | WeasyPrint |
| Auth | Auth.js v5 (credentials provider) |
| Scan AI | Gemini 2.0 Flash (free tier) |
| Toolkit AI | Claude API (Haiku) |
| Monitoring | Sentry + Flower |

---

## Section 1: Scan Engine

**Platform:** Gemini 2.0 Flash (free tier). Platform is stored as a field on every scan result — adding ChatGPT, Perplexity, Claude later requires no schema changes, only new platform configs.

**Query templates (static, 8 per client scan):**

| Category | Query 1 | Query 2 |
|---|---|---|
| Brand | "Tell me about [Brand]" | "What is [Brand] known for?" |
| Comparison | "[Brand] vs [Competitor 1]" | "Compare [Brand] and [Competitor 2]" |
| Recommendation | "Best [industry] in [location]" | "Top [industry] in [location]" |
| Local | "Best [industry] near me in [city]" | "[industry] services in [city]" |

Notes:
- Comparison queries use available competitors only. If fewer than 2 competitors exist, fill with available ones and skip remaining comparison queries.
- Queries are filled from client data: brand name, industry, city, state.

**Competitor scans:** 4 queries per competitor (1 per category, brand-focused). Full scan with 5 competitors = 8 + (5 × 4) = 28 Gemini calls. Within free tier limits.

**Brand detection:** Case-insensitive string match on brand name in response text.

**Scoring:** `(queries where brand detected / total queries) × 100`

**Execution:** Celery task, queued on manual trigger from admin panel. Retry once on API failure, flag scan as failed if second attempt fails. Raw response text stored for 90 days then purged.

---

## Section 2: Data Model

### clients
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| name | text | Brand name |
| website | text | |
| industry | text | |
| description | text | 3–5 sentences |
| target_audience | text | |
| city | text | |
| state | text | |
| contact_email | text | Where digests and PDFs are sent |
| brand_authority_score | int | 0–100, manually set by Faris |
| content_quality_score | int | 0–100, manually set by Faris |
| technical_foundations_verified | bool | Default false |
| structured_data_verified | bool | Default false |
| score_drop_threshold | int | Default 35, configurable per client |
| created_at | timestamptz | |
| archived_at | timestamptz | Nullable |

### competitors
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| client_id | uuid | FK → clients |
| name | text | |
| website | text | |

### scans
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| client_id | uuid | FK → clients |
| platform | text | Default "gemini" |
| status | text | pending / running / completed / failed |
| triggered_at | timestamptz | |
| completed_at | timestamptz | Nullable |

### scan_query_results
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| scan_id | uuid | FK → scans |
| competitor_id | uuid | Nullable FK → competitors. Null = client query |
| category | text | brand / comparison / recommendation / local |
| query_text | text | |
| response_text | text | Raw AI response, purged after 90 days |
| brand_detected | bool | |
| created_at | timestamptz | |

### geo_scores
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| client_id | uuid | FK → clients |
| scan_id | uuid | FK → scans |
| ai_citability | float | |
| brand_authority | float | Snapshot from clients row at compute time |
| content_quality | float | Snapshot from clients row at compute time |
| technical_foundations | float | 0 or 100 |
| structured_data | float | 0 or 100 |
| overall_score | float | Weighted sum |
| computed_at | timestamptz | |

### activity_log
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| client_id | uuid | FK → clients |
| event_type | text | scan_completed / score_change / hallucination_flagged / manual_note / alert_sent / pdf_sent / etc. |
| note | text | Plain text |
| created_at | timestamptz | |

### toolkit_files
| Field | Type | Notes |
|---|---|---|
| id | uuid | PK |
| client_id | uuid | FK → clients |
| file_type | text | llms_txt / schema_json / robots_txt |
| content | text | Generated file content |
| generated_at | timestamptz | |
| verified_at | timestamptz | Nullable — set when crawl confirms file is live |

---

## Section 3: GEO Scoring

**Computation:**
```
overall = (ai_citability    × 0.40)
        + (brand_authority  × 0.20)
        + (content_quality  × 0.20)
        + (technical_foundations × 0.10)
        + (structured_data  × 0.10)
```

**How each dimension is set:**

| Dimension | Source |
|---|---|
| AI Citability | Auto — computed after every scan from scan_query_results |
| Brand Authority | Manual — Faris inputs 0–100 monthly in admin panel |
| Content Quality | Manual — Faris inputs 0–100 monthly in admin panel |
| Technical Foundations | Auto — 0 until llms.txt + robots.txt verified → 100 |
| Structured Data | Auto — 0 until schema.json verified → 100 |

Manual dimensions always display label: **"Assessed by SeenBy team"**

**Score bands (SCORE_VERSION = "v1.0.0" — bump when weights change):**

| Score | Band | Color |
|---|---|---|
| 80–100 | Excellent | Green |
| 65–79 | Good | Green |
| 50–64 | Fair | Yellow |
| 35–49 | Developing | Yellow |
| 0–34 | Low | Red |

**Day one display:** All dimensions and overall score show `—` / "Awaiting first scan" until first scan completes.

**Score history:** Querying `geo_scores` over time by `client_id` provides full trend data.

---

## Section 4: Admin Panel

**Auth:** Auth.js v5 credentials provider. Single admin user — username + password in environment variables. Auth.js issues JWT, passed as Bearer token to FastAPI. FastAPI validates against shared JWT secret. No database-stored sessions.

**Routes (exact — no additions without updating CLAUDE.md):**
```
/                          → redirect to /clients
/auth/login                → login
/clients                   → all clients overview
/clients/[id]              → client overview (score + trend)
/clients/[id]/scan         → scan & visibility
/clients/[id]/competitors  → competitor intelligence
/clients/[id]/toolkit      → AI readiness toolkit
/clients/[id]/content-gaps → content gaps (topic + entity coverage, content quality assist)
/clients/[id]/reports      → reports
/clients/[id]/activity     → activity log
/clients/[id]/settings     → client settings
```

**Onboarding wizard (triggered via "Add Client" on /clients):**
- Step 1: Brand name + website + industry → creates client record immediately, score shows `—`
- Step 2: Up to 5 competitors
- Step 3: Description + target audience + location (unlocks toolkit)

Wizard can be exited after Step 1. Steps 2 and 3 completable later from settings. Client is scannable immediately after Step 1.

**/clients overview:** Each client card shows name, overall score (or `—`), score band color, last scan timestamp.

---

## Section 5: AI Readiness Toolkit

**Form:** Pre-populates from client data (Steps 1 + 3 of onboarding). Fields: business name, website, industry, description, services, city/state, target audience, optional existing robots.txt paste.

**Three generators via Claude Haiku:**
- `llms.txt` — describes the business for AI crawlers per Answer.AI spec
- `schema.json` — JSON-LD with LocalBusiness + Organization + FAQPage
- `robots.txt` — merges any existing rules + adds GPTBot, PerplexityBot, ClaudeBot, Google-Extended allow rules

**UX per output:** Copy to clipboard button, download as file button, plain English implementation instructions per file.

**Verification:** "Verify implementation" button per file. Makes a GET request to `clientdomain.com/[filename]`. 200 response = verified. Sets `verified_at` on the toolkit_files row and updates the client's verification booleans.

**Score updates on verification:**
- llms.txt + robots.txt verified → `technical_foundations_verified = true` → Technical Foundations = 100
- schema.json verified → `structured_data_verified = true` → Structured Data = 100
- Overall GEO score recomputes and saves a new `geo_scores` row automatically.

---

## Section 6: Reporting

### Weekly Email Digest (automated)

- Celery Beat runs every Monday
- For each client: checks if any scan completed in the past 7 days
- No scan that week → no email (skipped entirely)
- If scan found:
  - Current AI Citability score
  - Trend vs previous scan (up / down / flat)
  - "Seen by Gemini X out of 8 times this week"
  - Milestone callouts ("First time Gemini saw your brand")
  - Claude Haiku generates 1-sentence action recommendation **only** when score changed ±5pts vs previous scan — otherwise standard tip from predefined list
- Sent to: client's `contact_email`
- Sender: `contact@seenby.my`

### Monthly PDF Report (reviewed before sending)

- Celery Beat triggers 30 days after `clients.created_at`, repeats every 30 days
- WeasyPrint generates PDF from HTML template
- PDF saved to Supabase Storage
- Admin panel shows **"Ready for review"** badge on `/clients/[id]/reports`
- Notification email sent to `contact@seenby.my`
- Faris clicks **"Send to client"** → Resend dispatches PDF to client's `contact_email`

**PDF contents:**
- Overall GEO score + color band
- 5-dimension score breakdown with "Assessed by SeenBy team" labels on manual dimensions
- Platform breakdown: "Seen by AI" / "Not yet seen by AI" per platform
- Competitor section: "Your competitors are winning here" where applicable
- "What this means" plain English paragraph above every section
- "What to do next" — 3 specific actions
- Before/after comparison pulled from activity log

---

## Section 7: Alerts

All alerts sent to `contact@seenby.my` and create an `activity_log` entry automatically.

**Score drop alert:**
- Triggers after scan completes if overall score CROSSES below `score_drop_threshold` (was above, now below — fires once per crossing, not on every scan while below)
- Default threshold: 35. Configurable per client in settings.

**Competitor overtake alert:**
- Triggers after scan completes if any competitor's AI Citability score now exceeds the client's AI Citability score
- Email shows which competitor and the score delta

**Hallucination flag:**
- Manual trigger by Faris from scan results view
- Faris clicks "Flag hallucination" on a specific query result
- Creates activity_log entry + sends alert email with: query text, AI response, brand name

---

## Build Order

1. Core scan engine + GEO scoring
2. Admin panel + onboarding wizard
3. AI Readiness Toolkit + verification crawler
4. Competitor intelligence
5. Client activity log
6. Weekly email digest + Claude-generated actions
7. Monthly PDF report generator
8. Alerts system

---

## Explicitly Deferred (not MVP)

- Client dashboard login
- Self-serve signup and billing
- White-label reseller
- Multi-locale prompts
- Automated Brand Authority / Content Quality scoring
- Webhook integrations
- Scheduled / automated scans
- Additional AI platforms (ChatGPT, Perplexity, Claude API)
- Option 2 checklist scoring
- Option 3 automated technical scanning

---

## Language Rules (enforced everywhere — UI, email, PDF, comments)

| Never use | Always use |
|---|---|
| cited / uncited | Seen by AI / Not yet seen by AI |
| mentioned / not mentioned | Seen by AI / Not yet seen by AI |
| citation rate | visibility frequency |
| ranking position | AI Search Ranking |
| visibility gap | Your competitors are winning here |
| confidence score | (never surface to client) |
| char offset | (never surface to client) |
| token count | (never surface to client) |
| first mentioned | first seen by AI |

---

## Verification Plan

After each build phase, verify:

1. **Scan engine:** Trigger a manual scan, confirm 28 Gemini calls fire (8 client + 20 competitor), confirm `scan_query_results` rows are created, confirm `brand_detected` values are sensible, confirm `geo_scores` row is computed correctly.
2. **Admin panel:** Login flow works, all routes accessible, onboarding wizard creates correct DB rows, client card shows `—` before first scan.
3. **Toolkit:** All three files generate without error, copy/download work, verification GET fires and updates `verified_at` and scores.
4. **Competitor intelligence:** Competitor scores visible, overtake flag appears correctly.
5. **Activity log:** Manual notes save, scan events auto-log.
6. **Weekly digest:** Trigger Celery task manually for a client with a recent scan, confirm email received at client contact email with correct content.
7. **Monthly PDF:** Trigger PDF generation task, confirm file saved to Supabase Storage, confirm "Ready for review" badge appears, confirm "Send to client" dispatches email.
8. **Alerts:** Drop score below threshold manually (edit geo_scores row), trigger scan, confirm alert email received.
