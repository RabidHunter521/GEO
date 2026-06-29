# PDF Report Redesign — Design Spec
**Date:** 2026-06-29  
**Status:** Approved  
**File:** `backend/app/services/report_service.py`

---

## Goal

Redesign the monthly client PDF report from a functional HTML-to-PDF document into a premium, consulting-grade deliverable. The current report delivers the right content but reads as an office document. The redesign makes it feel earned — something a client receiving a retainer invoice would expect.

**Style target:** McKinsey / Deloitte consulting report.  
**Audience:** Malaysian SME clinic owners and similar retainer clients.  
**Renderer:** WeasyPrint (HTML + CSS + inline SVG — no JavaScript).

---

## 1. Foundation: Palette

| Role | Color | Hex |
|---|---|---|
| Cover background | Ink navy | `#070d1a` |
| Primary accent | Confident blue | `#2563eb` |
| Body background | White | `#ffffff` |
| Primary text | Near-black | `#0f172a` |
| Secondary text | Slate | `#64748b` |
| Dividers | Light grey | `#e2e8f0` |
| Running header bg | Ink navy | `#070d1a` |
| Score: excellent/good | Rich emerald | `#059669` |
| Score: fair/developing | Amber | `#d97706` |
| Score: low | Clear red | `#dc2626` |
| Pipeline box border | Teal | `#0891b2` |
| At-risk box border | Amber | `#d97706` |
| Dark arc track (gauge) | Dark slate | `#1e2d4a` |

The ink navy (`#070d1a`) is used exclusively for: cover background, running header. The blue accent (`#2563eb`) is used exclusively for: section header bars, recommended action box, score gauge fill when green. Restraint is the point — when blue appears, it signals.

---

## 2. Foundation: Typography

**Font:** Inter, loaded via Google Fonts `@import`. Fallback: `-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`.

| Element | Size | Weight | Case | Notes |
|---|---|---|---|---|
| Cover client name | 26pt | 700 | Title | White on dark |
| Cover score number | 52pt | 700 | — | White on dark |
| Cover narrative | 10.5pt | 400 | Sentence | `#cbd5e1`, italic |
| Section headers (h2) | 9.5pt | 700 | ALL CAPS | Letter-spacing 0.1em; 3px `#2563eb` left bar |
| Body text | 10pt | 400 | — | Line-height 1.6 |
| Table header row | 8pt | 600 | ALL CAPS | Letter-spacing 0.06em; white on `#070d1a` |
| Table body cells | 10pt | 400 | — | First column weight 600 |
| Stat labels | 8pt | 600 | ALL CAPS | `#64748b`, letter-spacing |
| Stat values | 26pt | 700 | — | `#0f172a` |
| Stat sublabels | 9.5pt | 400 | — | `#64748b` |
| Running header | 8.5pt | 400 | — | White on ink navy |
| Footer | 8pt | 400 | — | `#64748b` |
| Proof card tags | 8pt | 700 | ALL CAPS | Color-coded |

---

## 3. Page Frame

### Cover
- Full-bleed `#070d1a` background — no white, no panels
- Forced page break after (`page-break-after: always`)

### Body pages (all pages after cover)
**Running header** — implemented as a `position: fixed; top: 0; left: 0; right: 0` div. WeasyPrint repeats fixed-position elements on every page. A `@page` margin box cannot reliably carry a full-bleed colored background, so the fixed-div approach is preferred.
- Full-width `#070d1a` bar, height 28px, padding 0 2cm (matches page margin)
- Left: `SeenBy` in white 8.5pt weight 600
- Right: `[Client Name] · [Period]` in `#94a3b8` 8.5pt
- `z-index: 1000`; body `padding-top: 36px` to prevent overlap

**Running footer** — implemented as a `position: fixed; bottom: 0; left: 0; right: 0` div, same technique.
- Thin top border `#e2e8f0`; padding 4px 2cm; height 20px
- Left: `Confidential` in `#94a3b8`, 8pt
- Right: `Page X of Y` using WeasyPrint's native CSS counter — `content: counter(page) " of " counter(pages)` inside a `::after` pseudo-element on the footer div

---

## 4. Cover Page Layout

Top-to-bottom, all centered horizontally unless noted:

1. **SeenBy wordmark** — top-left, white, 20pt, weight 700
2. **3px horizontal rule** — full width, `#2563eb`
3. **`AI VISIBILITY INTELLIGENCE`** — `#94a3b8`, 8pt, uppercase, letter-spacing — below rule
4. *(40px gap)*
5. **`MONTHLY AI VISIBILITY REPORT`** — `#94a3b8`, 8.5pt, uppercase, heavy letter-spacing — left-aligned
6. **Client name** — white, 26pt, weight 700 — left-aligned
7. **Period label** — `#94a3b8`, 11pt — left-aligned (e.g. *"June 2026"*)
8. *(56px gap)*
9. **Score gauge SVG** — centered, 240px wide (see Section 6)
10. **Score number** — white, 52pt, weight 700 — centered, below gauge
11. **`GEO SCORE · GOOD`** — `#94a3b8`, 9pt, uppercase — centered
12. *(40px gap)*
13. **Change narrative** — `#cbd5e1`, 10.5pt, italic, centered, max-width 440px
14. *(flex spacer to push footer down)*
15. **Cover footer** — thin top rule `#1e2d4a`; `Report generated 29 June 2026 · contact@seenby.my` in `#475569`, 8pt

---

## 5. Section Order (Narrative Arc)

Sections appear in this order in the body. Each has a psychological job.

| # | Section | Job |
|---|---|---|
| 1 | AI Visibility Score + Score Trend chart | Anchor with the number. Show movement. |
| 2 | What AI Said About You (proof cards) | Make the score real with verbatim evidence. |
| 3 | Score Breakdown (dimension bars) | Explain the number — reader is now engaged. |
| 4 | AI Visibility Frequency + Platform Breakdown | Granular data beneath the score. |
| 5 | AI Referral Traffic — visitors + pipeline | Connect visibility to business value earned. |
| 6 | Estimated Pipeline Still On The Table | Loss aversion immediately after pipeline. |
| 7 | The Battle To Win Next | Competitive urgency. One rival, one move. |
| 8 | Competitor Comparison | Full competitive picture. |
| 9 | Your Competitors Are Winning Here | Actionable content gaps. |
| 10 | Inaccurate AI Answers Flagged | Remediation grouped near gaps. |
| 11 | AI Readiness Toolkit | Technical compliance. Closes evidence loop. |
| 12 | Recommended Action | Always last. The one thing to do next. |

**Removed:** "What Changed This Month" body section. The Claude narrative appears on the cover only — showing it twice read as padding.

---

## 6. Score Gauge SVG (Cover)

Inline SVG semicircle gauge. Two overlapping arcs on the same path radius.

**Geometry:**
- `viewBox="0 0 240 130"`
- Center: `cx=120`, `cy=120` (bottom of viewBox so arc opens upward)
- Arc radius: `r=100`, stroke-width: `20`
- Left endpoint: `(20, 120)`, right endpoint: `(220, 120)`

**Background track arc:**
```
M 20,120 A 100,100 0 0,1 220,120
stroke="#1e2d4a" stroke-width="20" fill="none"
```

**Score fill arc:**
```
M 20,120 A 100,100 0 [large_arc],1 [ex],[ey]
stroke=[score_color] stroke-width="20" fill="none" stroke-linecap="round"
```

**Endpoint calculation (Python):**
```python
import math
angle = math.pi - (score / 100.0) * math.pi
ex = 120 + 100 * math.cos(angle)
ey = 120 - 100 * math.sin(angle)
large_arc = 0  # always 0 for scores 0–100 (arc never exceeds 180°)
```

**Edge case:** score = 0 produces a degenerate arc (start = end). Clamp display minimum to `score = 1` for SVG rendering. Score = 100 uses `large_arc = 0` (both values produce identical 180° arc).

**Score color mapping:**
- 70–100 → `#059669`
- 30–69 → `#d97706`
- 0–29 → `#dc2626`

The score number and band label are HTML elements below the SVG, not inside it — WeasyPrint handles mixed HTML/SVG layout cleanly.

---

## 7. Body Element Designs

### Section Headers (h2)
```css
h2 {
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #0f172a;
  border-left: 3px solid #2563eb;
  padding-left: 10px;
  margin-top: 28px;
  margin-bottom: 14px;
  border-bottom: none;  /* removes current style */
}
```

### General Tables
- Header row: `background: #070d1a; color: #ffffff; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.06em`
- Even rows: `background: #f8fafc`
- Odd rows: `background: #ffffff`
- Cell padding: `10px 14px`
- First column: `font-weight: 600`
- No vertical borders — horizontal only (`border-bottom: 1px solid #f1f5f9`)

### Score Breakdown (replaces table)
Row-per-dimension layout. For each dimension:
```
[Name, 10pt, weight 600]        [Score, 10pt, weight 700, color-coded]  [Weight, 9pt, #94a3b8]
[████████████████░░░░░░] ← inline SVG bar
[Source note, 8.5pt, #94a3b8]
```

Bar SVG: `viewBox="0 0 400 10"`. Background rect `#e2e8f0` full width `rx=5`. Fill rect `width = score/100 * 400`, score-colored, `rx=5`. Rendered at `width: 100%`.

**Removed:** Contribution column (confusing to clients; weight already tells the story).

### Stat Boxes (standard)
Replace grey background box with typography-only:
```
[thin top rule: #e2e8f0]
LABEL — #64748b, 8pt, uppercase, letter-spacing
VALUE — #0f172a, 26pt, weight 700
Sub-line — #64748b, 9.5pt
```
No background container.

### Special Stat Boxes (pipeline / at-risk / battle)
4px left border in accent color + very light background tint:
- Pipeline: border `#0891b2`, background `#f0f9ff`
- At-risk: border `#d97706`, background `#fffbeb`
- Battle: inverted — `#070d1a` background, white text, `#2563eb` accent on the move line

### Proof Cards
Border-left only (no background color):
- **Win:** 4px `#059669` left border. Tag: `SEEN BY AI · [PLATFORM]` in `#059669`, 8pt, weight 700, uppercase. Quote: `#1e293b`, 10.5pt, italic.
- **Loss:** 4px `#d97706` left border. Tag: `WHO [PLATFORM] RECOMMENDED INSTEAD` in `#d97706`, 8pt, weight 700, uppercase. Quote: same treatment.

### Score Trend Chart
Keep existing SVG bar chart. Upgrades only:
- Bar corner radius: `rx=6` (up from 4)
- Date labels: `#94a3b8` (lighter)
- Container: `1px solid #e2e8f0` border, white background, `16px` padding — no grey fill

### Recommended Action (final section)
```css
.rec-box {
  border-left: 4px solid #2563eb;
  background: #eff6ff;
  padding: 14px 16px;
  border-radius: 0 4px 4px 0;
}
```
Label: `RECOMMENDED ACTION` — `#2563eb`, 8pt, uppercase, weight 700, display block above body text.
Body text: `#1e3a8a`, 11pt.

---

## 8. Implementation Scope

All changes are confined to `backend/app/services/report_service.py`:

1. **`_CSS` constant** — full replacement with new palette, Inter `@import`, `@page` rules (header/footer), new h2, table, stat box, proof card, rec box styles
2. **`_SCORECARD_CSS` constant** — aligned updates (font, palette)
3. **`_build_trend_svg()`** — minor upgrades (rx, label color, container)
4. **New `_build_gauge_svg(score)`** — generates the semicircle gauge SVG
5. **`_build_report_html()`** — section reorder, new stat box markup, new score breakdown markup, remove duplicate narrative section, add gauge to cover, update proof cards, update rec box
6. **`_build_scorecard_html()`** — font + palette alignment
7. **`_build_proof_html()`** — updated markup for border-left card design
8. **`_build_battle_html()`** — updated markup for inverted dark box

No schema changes. No new dependencies. No API changes. WeasyPrint already installed.

---

## 9. Out of Scope

- Client logo embedding (no logo upload feature in MVP)
- White-label theming
- Interactive elements
- Scorecard redesign beyond font/palette alignment
- Any changes to report data gathering logic
