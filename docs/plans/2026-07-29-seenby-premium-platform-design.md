# SeenBy Premium Platform Product Design

**Date:** 2026-07-29
**Status:** Approved product blueprint
**Product model:** Managed platform operated by SeenBy administrators, with secure read-only client views
**Initial markets:** Healthcare, F&B, and local services

## 1. Executive summary

SeenBy will evolve from a broad collection of GEO/AEO modules into a coherent
AI Visibility and Reputation Operating System.

The product will remain horizontal at its core. Healthcare, F&B, and local
services will be implemented as industry intelligence packs that extend a
shared data and workflow model. SeenBy will not be positioned as a
healthcare-only platform.

The primary product promise is:

> SeenBy helps businesses become visible, accurate, and preferred across AI
> search—and proves the work and business impact behind every improvement.

The redesign is evolutionary rather than destructive. Existing backend
services, database models, APIs, historical client records, and specialist
capabilities will be preserved. The user experience will consolidate them into
an evidence-to-outcome journey.

## 2. Product principles

1. **Outcomes over modules.** Clients should understand what changed, what
   matters, what SeenBy is doing, and what impact it produced.
2. **Evidence over unsupported certainty.** Observations, estimates,
   attribution, and causality must be labelled distinctly.
3. **Horizontal core, vertical intelligence.** Industry specialization should
   extend shared primitives rather than fork the application.
4. **Progressive disclosure.** Summaries and decisions come first; raw query,
   source, and competitor evidence remains available through drill-downs.
5. **Human review at risk boundaries.** Automation can collect, draft, and
   assemble, but it must not silently confirm risky facts or publish sensitive
   claims.
6. **Preserve data and capability.** Navigation consolidation must not cause
   destructive backend rewrites or historical data loss.
7. **Mobile for consumption, desktop for administration.** Client reporting
   and approvals must be excellent on mobile. Complex configuration remains
   desktop-first.

## 3. Product category and positioning

### Category

**AI Visibility and Reputation Operating System**

GEO/AEO monitoring remains a foundational capability, but it is not the whole
product category. SeenBy connects diagnosis, prioritization, delivery,
verification, and business proof.

### Four client outcomes

1. **Visibility:** Is the business found and recommended by AI platforms?
2. **Accuracy:** Are its facts, services, locations, and claims represented
   correctly?
3. **Preference:** Why are competitors selected, and which battles are worth
   winning?
4. **Impact:** What work was delivered, what changed, and what business value
   followed?

## 4. Product architecture

### Horizontal SeenBy Core

Every industry uses the same platform engine:

- Multi-platform AI visibility monitoring
- Buyer-query and opportunity intelligence
- Competitor win/loss analysis
- Citation and source provenance
- Truth and misinformation monitoring
- Content, authority, technical, and local-presence actions
- Review, approval, publication, and verification workflow
- AI traffic, lead, and revenue attribution
- Reports, benchmarks, and client proof

### Product hierarchy

```text
SeenBy
├── Intelligence
│   ├── AI Presence
│   ├── Buyer Queries
│   ├── Competitors
│   └── Sources
├── Reputation
│   ├── Business Truth Vault
│   ├── Accuracy Monitoring
│   ├── Authority
│   └── Technical Foundations
├── Growth
│   ├── Opportunities
│   ├── Content Plan
│   └── Content Production
├── Delivery
│   ├── Action Plan
│   ├── Approvals
│   └── Completed Work
├── Proof
│   ├── Progress
│   ├── Business Impact
│   └── Reports
└── Setup
```

### Current-to-future module mapping

| Current module | Future destination | Treatment |
| --- | --- | --- |
| Overview | Command Center | Redesign around outcomes |
| Checklist | Delivery / Action Plan | Consolidate |
| Scan & Visibility | Intelligence / AI Presence | Preserve and summarize |
| Competitor Intelligence | Intelligence / Competitors | Preserve |
| AI Readiness Toolkit | Reputation / Technical Foundations | Preserve; correct claims |
| Content Gaps | Growth / Opportunities | Consolidate |
| Content Roadmap | Growth / Content Plan | Consolidate and extend |
| Content Studio | Growth / Content Production | Preserve and connect |
| Authority & Presence | Reputation / Authority | Preserve and specialize |
| Reports | Proof / Reports | Preserve and automate |
| Activity Log | Proof / Progress | Convert to client-safe stories |
| Settings | Setup | Preserve and section |
| Gap Matrix | Portfolio Intelligence | Preserve for administrators |
| Review Queue | Delivery / Approvals | Expand into operational inbox |

Standalone pages may become grouped tabs or drill-downs. Existing routes should
remain temporarily compatible during migration.

## 5. Measurement model

SeenBy will separate four measurement layers instead of presenting one score as
if it represents every kind of progress.

### 5.1 AI Presence

Primary outcome metric:

- Mention rate
- Recommendation rate
- Shortlist or first-position presence
- Platform coverage
- Citation presence
- Competitor share of voice
- Commercial-intent visibility
- Local-market visibility

The client headline should use plain evidence, for example:

> Seen in 32 of 71 tracked buyer questions.

### 5.2 Accuracy and Reputation

Measures whether AI representations agree with approved business facts.

Finding severities:

- Critical
- High
- Medium
- Low

Potential findings remain **needs review** until a human confirms them.
Severity rules vary by intelligence pack.

### 5.3 Growth Readiness

The existing GEO score and dimensions will migrate toward this leading
indicator. It covers:

- Content coverage
- Page citability
- Entity clarity
- Structured data
- Crawl accessibility
- Source authority
- Profile consistency
- Local-presence completeness
- Business Truth Vault completeness

Technical file verification must not be presented as observed visibility.
`llms.txt` may remain an optional publishing asset, but it must not imply a
guaranteed ranking or visibility effect.

### 5.4 Business Impact

Measures traffic, intent events, leads, bookings, orders, and revenue.

Values must be labelled:

- Observed
- Attributed
- Assisted
- Estimated

Estimated pipeline must never be styled as confirmed revenue.

### 5.5 Measurement confidence

AI answers can vary between runs. SeenBy will introduce:

- Emerging
- Repeated
- Stable
- Volatile
- Insufficient data

The initial repeat-sampling strategy should focus on high-value queries, recent
changes, and factual risks rather than multiplying the cost of every scan.

## 6. Admin and client experiences

### Admin workspace

Global workspace:

- All Clients
- Portfolio Intelligence
- Review Queue
- Client Health

Selected-client workspace:

- Command Center
- Intelligence
- Reputation
- Growth
- Delivery
- Proof
- Setup

The admin Command Center answers:

1. What changed?
2. What needs attention?
3. What should be done next?
4. What is currently being delivered?
5. What value has been produced?

The top outcome row contains AI Presence, Accuracy Health, Growth Readiness,
and Business Impact.

Portfolio health should surface clients with meaningful visibility losses,
critical accuracy risks, overdue delivery items, stale scans, missing monthly
proof, upcoming reports, and scan or API budget warnings.

### Client portal

Client navigation is deliberately smaller:

- Overview
- Visibility
- Reputation
- Action Plan
- Progress
- Reports

The Overview order is:

1. What changed
2. Business impact
3. Important wins
4. Important risks
5. Work underway
6. Next actions
7. Trends

Large query, source, and competitor tables begin with meaningful segments and
filters. Raw evidence is available through drill-downs.

Empty client modules should be hidden, replaced with scheduled-state messaging,
or shown only when included in the service plan.

The client portal is a mobile consumption experience: one-column outcome cards,
collapsible evidence, large touch targets, and a compact selector replace
clipped tabs and wide default tables.

## 7. Unified delivery and outcome workflow

### Outcome Action

A lightweight Outcome Action layer links current specialist records without
replacing them.

Each action contains:

- Client, brand, and location
- Industry pack
- Action type
- Source evidence
- Business objective
- Priority and confidence
- Owner and due date
- Workflow status
- Deliverable or destination URL
- Approval record
- Publication date
- Verification scan
- Measured outcome
- Client-safe summary

### Action types

- Content creation or improvement
- Technical foundation
- Structured data
- Business fact correction
- Accuracy investigation
- Authority and citation development
- Local listing or profile improvement
- Competitor-response action
- Measurement or tracking setup

### Lifecycle

```text
Detected
→ Recommended
→ Approved internally
→ In progress
→ Waiting for client
→ Ready to publish
→ Published
→ Waiting for verification
→ Verified / No observed change
```

Other terminal states include superseded and dismissed with reason.

### Priority model

Priority is explainable and considers:

- Commercial intent
- Current visibility gap
- Competitor advantage
- Factual or reputational risk
- Buyer demand
- Expected influence
- Confidence
- Effort
- Service-plan eligibility

### Human approval boundaries

Human review is required before:

- Confirming accuracy or misinformation findings
- Publishing client content
- Changing approved truth facts
- Making healthcare, halal, licensing, or regulatory claims
- Marking work as completed
- Releasing a final high-value client report

Scheduled scans, evidence collection, drafts, reminders, verification rescans,
report assembly, and anomaly detection may be automated.

### Proof chain

Every action should be capable of displaying:

```text
Evidence
→ Decision
→ Work delivered
→ Publication
→ Verification
→ Business outcome
```

The interface must distinguish verified correlation from defensible causality.

### Managed delivery cadence

- Continuous monitoring
- Weekly risk and opportunity review
- Monthly delivery cycle
- Verification after publication
- Monthly progress summary
- Quarterly strategy and benchmark review

## 8. Business Truth Vault

### Shared facts

- Official and trading names
- Aliases and previous names
- Description and positioning
- Products and services
- Locations and service areas
- Opening and holiday hours
- Contact, booking, and ordering channels
- Pricing guidance
- Credentials and certifications
- Policies and restrictions
- Approved and prohibited claims
- Authoritative source URLs
- Verification date, owner, and approval history

Facts are versioned so historical scans can be compared against the facts that
were valid at the time.

### Location hierarchy

```text
Brand
├── Shared facts
├── Location A
│   ├── Local services
│   ├── Hours
│   ├── Staff
│   └── Profiles
├── Location B
└── Location C
```

A single-location account is a brand with one location. The same model supports
private multi-location groups.

## 9. Industry intelligence packs

Packs extend schemas, query generation, risk rules, source selection,
competitor classification, content recommendations, benchmarks, and report
language. They do not fork the application.

### Healthcare

Entities:

- Clinicians and practitioners
- Specialties
- Treatments and procedures
- Qualifications and registrations
- Accreditations
- Facilities
- Insurance and payment options

Risks include invented treatments, incorrect credentials, unsafe claims,
incorrect practitioner associations, and unsupported outcome claims.

### F&B

Entities:

- Outlets
- Menus and menu items
- Cuisine types
- Dietary options
- Halal status and certification
- Price range
- Reservations
- Delivery and takeaway channels
- Facilities and occasions
- Operating and kitchen hours

Risks include incorrect halal status, outdated hours, incorrect menu or price
information, invented dietary options, and outlet confusion.

### Local Services

Selectable subcategories include home maintenance, automotive, beauty and
wellness, cleaning, repair, professional local services, and emergency
services.

Entities:

- Service catalog
- Coverage areas
- Availability
- Emergency or same-day service
- Licensing and insurance
- Pricing model
- Warranties
- Response time
- Service exclusions
- Booking channels

Risks include incorrect coverage, false availability, invented emergency
service, unsupported licensing, and misleading price promises.

### Query universe

Tracked questions combine:

- Industry-pack templates
- Client services and locations
- Search Console data
- Website content
- Customer reviews
- Sales and support questions
- Competitor topics
- AI-cited sources
- Curated strategic questions

Tags include buyer stage, commercial intent, location, language, service,
risk sensitivity, estimated opportunity, and tracking priority.

### Professional and compliance boundary

Industry packs provide domain structure, evidence, and review routing. They do
not provide medical, legal, halal-certification, or regulatory approval.
SeenBy may identify a conflict with an approved business fact and require
review; it must not declare a legal or professional violation unless a
qualified reviewer has confirmed it.

### Benchmark peer model

Comparisons should use meaningful peer groups based on industry pack,
subcategory, geography, business or group size, number of locations,
measurement coverage, and comparable time period. Every published benchmark
must disclose the peer count and period. No benchmark is exposed below a
defined minimum sample size.

## 10. Attribution and reporting

### Attribution ladder

1. Visibility evidence
2. Traffic evidence
3. Intent evidence
4. Lead and conversion evidence

Higher levels support stronger business-impact claims.

### Integrations

Foundation:

- Google Analytics 4
- Google Search Console
- Google Business Profile
- Tag Manager or equivalent event setup
- CSV import

Next layer:

- Call tracking
- WhatsApp and messaging events
- Booking and reservation systems
- Form and lead platforms
- CRM systems
- Ordering and delivery links

A flexible event-mapping layer should normalize external events into SeenBy
event categories rather than requiring bespoke integration logic everywhere.

### Monthly report

1. Executive summary
2. AI Presence
3. Accuracy and Reputation
4. Work Delivered
5. Verified Outcomes
6. Business Impact
7. Next 30 Days

Quarterly strategy reviews add benchmarks, competitor movement, query changes,
location performance, Truth Vault freshness, and strategic recommendations.

All generated narrative must use stored metrics, state the comparison period,
separate observed and estimated outcomes, avoid unsupported causality, and link
important claims to evidence.

## 11. Commercial packaging

### SeenBy Assessment

Paid diagnostic with baseline AI Presence, accuracy review, Growth Readiness,
competitor snapshot, priority opportunity map, Truth Vault starter, and a
90-day recommended plan.

### SeenBy Core

For single-location businesses: scheduled monitoring, one intelligence pack,
Truth Vault, competitor tracking, monthly reporting, action plan, limited
delivery capacity, and a client portal.

### SeenBy Growth

Flagship premium package: weekly review, content production, authority and
local-presence actions, accuracy remediation, impact tracking, approvals,
verification rescans, monthly strategy narrative, quarterly benchmark review,
and higher delivery capacity.

### SeenBy Leader

For private multi-location groups: location hierarchy and comparison, multiple
market competitors, advanced benchmarks, custom reports, attribution
integrations, service-level commitments, higher scan frequency, and optional
API access.

Feature gating should focus on scan frequency, query and competitor coverage,
locations, delivery capacity, integrations, retention, report customization,
and API access. Core evidence should not be hidden behind confusing locked
modules.

SeenBy may guarantee controllable delivery and process commitments. It must not
guarantee rankings, model recommendations, a fixed visibility increase, or a
specific revenue outcome.

## 12. Prioritized roadmap

### Phase 0: Accuracy, trust, and reliability

- Correct Toolkit claims and score implications
- Separate observed, attributed, and estimated values
- Replace raw client-facing activity labels
- Improve empty Progress and Report states
- Remove test/prospect data from production-facing views
- Fix the order-dependent backend test
- Resolve documentation drift
- Establish metric and methodology versioning

### Phase 1: Coherent premium experience

- Grouped navigation
- Admin Command Center
- Shorter client Overview
- Progressive disclosure
- Four-layer metric hierarchy
- Improved mobile client navigation
- Dynamic client modules
- Monthly client narrative

### Phase 2: Delivery operating system

- Outcome Action model
- Evidence links
- Explainable priority
- Owners, dates, statuses
- Unified Review Queue
- Publication and verification
- Secure approval links
- Service-plan delivery rules

### Phase 3: Truth and location foundation

- Versioned Business Truth Vault
- Brand and location hierarchy
- Fact freshness and verification
- Accuracy comparison
- Location performance
- Truth-aware content generation

### Phase 4: Intelligence packs

- Healthcare
- F&B
- Local Services

Each pack begins with curated administrator-reviewed schemas and rules.

### Phase 5: Measurement quality and business proof

- Repeat sampling and confidence states
- Buyer-demand enrichment
- Commercial-intent ranking
- Search Console and Business Profile integration
- Conversion-event mapping
- Actual-versus-estimated reporting

### Phase 6: Benchmark and data moat

- Industry, local, and location benchmarks
- Quarterly SEA AI Visibility Index
- Source-influence trends
- Query-demand movement
- Anonymous aggregate insights

Benchmarks require a disclosed minimum peer count.

## 13. Explicit non-goals

The initial roadmap will not prioritize:

- Twenty or more AI engines
- A massive global prompt database
- Full self-serve onboarding
- Unreviewed automatic publishing
- Complex client user management
- Hospital-enterprise procurement features
- Dozens of direct integrations
- `llms.txt` as a primary differentiator
- Guaranteed rankings or visibility increases
- Precise revenue claims from incomplete analytics
- Every possible industry pack

## 14. Success measures

- Time from onboarding to first useful insight
- Time from insight to approved action
- Percentage of actions completed on time
- Percentage of published actions verified
- Percentage of clients with visible monthly progress
- Percentage of reports containing actual outcomes
- Critical accuracy-risk resolution time
- Retention and service expansion
- Delivery capacity per administrator
- Scan cost per managed account
- Percentage of tracked queries with stable measurements

## 15. Migration and compatibility requirements

1. Preserve existing database records and specialist services.
2. Add the Outcome Action layer as references to existing records.
3. Introduce grouped navigation over current routes.
4. Build summary experiences over existing data.
5. Keep old routes during migration.
6. Version score and methodology changes.
7. Verify historical reports before changing labels or calculations.
8. Measure usage and achieve feature parity before removing old UI.
9. Use reversible migrations and backfills for new truth and location models.
10. Do not expose partial, unreviewed industry-pack classifications to clients.

## 16. Initial release definition

The first major release should combine:

1. Trust and reliability corrections
2. Command Center and navigation consolidation
3. Unified delivery workflow
4. Business Truth Vault foundation

This sequence makes the current breadth coherent before adding further feature
surface. The three intelligence packs then extend a proven horizontal system.

## 17. Research context

The design accounts for a market that now combines monitoring, content action,
audits, APIs, prompt intelligence, and agent experience. It deliberately avoids
competing only on platform count or raw prompt volume.

Relevant current sources:

- Google generative AI optimization guidance:
  https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- OpenAI publisher guidance:
  https://help.openai.com/en/articles/12627856
- Ahrefs Brand Radar:
  https://ahrefs.com/brand-radar
- Profound features:
  https://www.tryprofound.com/features
- Scrunch:
  https://scrunch.com/
- Otterly pricing and feature coverage:
  https://help.otterly.ai/pricing-of-otterlyai
- "Don't Measure Once":
  https://arxiv.org/abs/2604.07585
