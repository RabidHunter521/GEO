# Verbatim AI Answer Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the existing (admin-only) AI-answer snippet capability into the read-only client view as live HTML "win/loss" answer cards on the overview and scan pages.

**Architecture:** Compute server-side (Approach A). A new `proof_card_service` layers on the existing `snippet_service` to select and build redacted, sentence-level excerpts. The public client-view API attaches only `{kind, platform_label, category, excerpt}` — `response_text` never leaves the server. The frontend renders live, accessible HTML cards.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (backend), pytest (tests), Next.js 15 + shadcn/ui + Tailwind (frontend).

## Global Constraints

- Language rules (CLAUDE.md §2): use "Seen by AI" / "Not seen by AI", "recommended a competitor", "you weren't mentioned". NEVER "cited", "mentioned", "citation", "ranking position".
- Client-view surface is a strict whitelist (CLAUDE.md §8): NEVER expose `response_text`, confidence scores, char offsets, token counts, or raw AI responses. Only the redacted, sentence-level `excerpt` string may cross to the client surface.
- Backend: business logic in `app/services/`, never in routes. Constants in `app/core/constants.py`. No schema/DB change in this feature (compute-on-read).
- Frontend: shadcn/ui only; all types in `src/types/index.ts`; score colors/tokens from existing CSS tokens (`score-strong`, `score-watch`), never hardcoded.
- Excerpt cap on overview: 2 wins + 1 loss. Loss cards restricted to `recommendation`/`local` categories.
- Competitor names redact to the literal string `[a competitor]` (reuse existing `snippet_service._redact`).

---

### Task 1: Loss-excerpt extractor in snippet_service

**Files:**
- Modify: `backend/app/services/snippet_service.py`
- Test: `backend/tests/test_snippet_service.py`

**Interfaces:**
- Consumes: existing `_redact(text, competitors)`, `_brand_pattern(brand)`, `_MAX_EXCERPT_CHARS` in `snippet_service.py`.
- Produces: `build_loss_excerpt(response_text: str, brand: str, competitors: list[str]) -> str | None` — returns the first sentence naming a competitor (that name redacted to `[a competitor]`, truncated to `_MAX_EXCERPT_CHARS`) ONLY when the brand is absent and a competitor is present; else `None`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_snippet_service.py`:

```python
from app.services.snippet_service import build_loss_excerpt


def test_build_loss_excerpt_redacts_competitor_when_brand_absent():
    response = "For dental care in KL, RivalCo is the most recommended clinic. They have great reviews."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result == "For dental care in KL, [a competitor] is the most recommended clinic."


def test_build_loss_excerpt_none_when_brand_present():
    response = "Acme Dental and RivalCo are both strong choices in KL."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_none_when_no_competitor_named():
    response = "There are many good dental clinics in KL to choose from."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_none_when_no_competitors_configured():
    response = "RivalCo is the most recommended clinic in KL."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=[]) is None


def test_build_loss_excerpt_empty_text():
    assert build_loss_excerpt("", brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_truncates_long_sentence():
    long_sentence = "RivalCo " + "is widely recommended " * 40 + "in KL."
    result = build_loss_excerpt(long_sentence, brand="Acme Dental", competitors=["RivalCo"])
    assert result is not None and len(result) <= 280 and result.endswith("…")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_snippet_service.py -k build_loss_excerpt -v`
Expected: FAIL with `ImportError` / `cannot import name 'build_loss_excerpt'`.

- [ ] **Step 3: Implement build_loss_excerpt**

Add to `backend/app/services/snippet_service.py` (after `build_excerpt`):

```python
def build_loss_excerpt(response_text: str, brand: str, competitors: list[str]) -> str | None:
    """Sentence naming a competitor, shown only when the brand is ABSENT.

    The competitor name is redacted to '[a competitor]' so the card never
    promotes a rival — it says 'AI recommended a competitor, not you'. Returns
    None when the text is empty, the brand appears (that's a win, not a loss),
    no competitor is configured, or no competitor is named in the text."""
    if not response_text:
        return None
    names = [c for c in competitors if c]
    if not names:
        return None
    if _brand_pattern(brand).search(response_text):
        return None
    comp_pattern = re.compile(
        "|".join(rf"\b{re.escape(n)}\b" for n in names), re.IGNORECASE
    )
    sentences = re.split(r"(?<=[.!?])\s+", response_text.strip())
    chosen = next((s for s in sentences if comp_pattern.search(s)), None)
    if chosen is None:
        return None
    chosen = _redact(chosen.strip(), names)
    if len(chosen) > _MAX_EXCERPT_CHARS:
        chosen = chosen[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    return chosen
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_snippet_service.py -v`
Expected: PASS (all snippet tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/snippet_service.py backend/tests/test_snippet_service.py
git commit -m "feat(snippet): loss-excerpt extractor for competitor-won answers"
```

---

### Task 2: proof_card_service — selection logic

**Files:**
- Create: `backend/app/services/proof_card_service.py`
- Test: `backend/tests/test_proof_card_service.py`

**Interfaces:**
- Consumes: `snippet_service.build_excerpt`, `snippet_service.build_loss_excerpt`; `ScanQueryResult` rows (attributes used: `platform`, `category`, `brand_detected`, `recommendation_position`, `response_text`).
- Produces:
  - `@dataclass ProofCard{ kind: str, platform: str, category: str, excerpt: str }` (`kind` is `"win"`|`"loss"`, `platform` is the raw platform code).
  - `result_excerpt(result, brand: str, competitors: list[str]) -> tuple[str | None, str | None]` → `(kind, excerpt)` or `(None, None)`.
  - `select_proof_cards(results, brand: str, competitors: list[str], win_cap: int = 2, loss_cap: int = 1) -> list[ProofCard]` → wins first, then losses, capped.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_proof_card_service.py`:

```python
from dataclasses import dataclass

from app.services.proof_card_service import (
    ProofCard,
    result_excerpt,
    select_proof_cards,
)


@dataclass
class FakeResult:
    platform: str
    category: str
    brand_detected: bool
    recommendation_position: int | None
    response_text: str | None


def _win(platform="chatgpt", category="recommendation", pos=1):
    return FakeResult(platform, category, True, pos,
                      "Acme Dental is the top recommended clinic in KL.")


def _loss(platform="perplexity", category="local"):
    return FakeResult(platform, category, False, None,
                      "In KL, RivalCo is the most recommended dental clinic.")


def test_result_excerpt_win():
    kind, ex = result_excerpt(_win(), "Acme Dental", ["RivalCo"])
    assert kind == "win" and "Acme Dental" in ex


def test_result_excerpt_loss_redacts_competitor():
    kind, ex = result_excerpt(_loss(), "Acme Dental", ["RivalCo"])
    assert kind == "loss" and "[a competitor]" in ex and "RivalCo" not in ex


def test_result_excerpt_none_for_absent_brand_in_brand_category():
    r = FakeResult("chatgpt", "brand", False, None, "RivalCo is great.")
    assert result_excerpt(r, "Acme Dental", ["RivalCo"]) == (None, None)


def test_select_caps_two_wins_one_loss():
    results = [_win(pos=1), _win(pos=2), _win(pos=3), _loss(), _loss()]
    cards = select_proof_cards(results, "Acme Dental", ["RivalCo"])
    assert [c.kind for c in cards] == ["win", "win", "loss"]


def test_select_orders_wins_before_losses():
    cards = select_proof_cards([_loss(), _win()], "Acme Dental", ["RivalCo"])
    assert cards[0].kind == "win" and cards[-1].kind == "loss"


def test_select_empty_when_no_qualifying_results():
    r = FakeResult("chatgpt", "comparison", False, None, "Many clinics exist.")
    assert select_proof_cards([r], "Acme Dental", ["RivalCo"]) == []


def test_proof_card_never_contains_response_text():
    cards = select_proof_cards([_win()], "Acme Dental", ["RivalCo"])
    assert all(not hasattr(c, "response_text") for c in cards)
    assert all(isinstance(c.excerpt, str) for c in cards)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_proof_card_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.proof_card_service`.

- [ ] **Step 3: Implement proof_card_service**

Create `backend/app/services/proof_card_service.py`:

```python
"""Select client-safe 'proof cards' from a scan's client-owned results.

A proof card is one verbatim AI answer, reduced to a single redacted sentence:
a WIN (the brand is named) or a LOSS (a competitor is named and the brand is
absent). The raw response_text is never carried on a ProofCard — only the
finished, redacted excerpt — so this can feed the public client view directly.
"""
from dataclasses import dataclass

from app.services import snippet_service

# Lower rank = surfaced first. Recommendation/local are the answers that read as
# "who got recommended", so they make the strongest proof.
_CATEGORY_PRIORITY = {"recommendation": 0, "local": 1, "brand": 2, "comparison": 3}
_LOSS_CATEGORIES = {"recommendation", "local"}


@dataclass
class ProofCard:
    kind: str       # "win" | "loss"
    platform: str   # raw platform code (caller maps to a label)
    category: str
    excerpt: str


def _sort_key(result) -> tuple[int, int]:
    cat_rank = _CATEGORY_PRIORITY.get(result.category, 9)
    pos = result.recommendation_position if result.recommendation_position is not None else 99
    return (cat_rank, pos)


def result_excerpt(result, brand: str, competitors: list[str]) -> tuple[str | None, str | None]:
    """(kind, excerpt) for one client-owned result, or (None, None)."""
    if result.brand_detected:
        ex = snippet_service.build_excerpt(result.response_text or "", brand, competitors)
        return ("win", ex) if ex else (None, None)
    if result.category in _LOSS_CATEGORIES:
        ex = snippet_service.build_loss_excerpt(result.response_text or "", brand, competitors)
        return ("loss", ex) if ex else (None, None)
    return (None, None)


def select_proof_cards(
    results,
    brand: str,
    competitors: list[str],
    win_cap: int = 2,
    loss_cap: int = 1,
) -> list[ProofCard]:
    """Best wins first, then the best loss, capped. Empty when nothing qualifies."""
    wins: list[ProofCard] = []
    losses: list[ProofCard] = []
    for r in sorted(results, key=_sort_key):
        kind, ex = result_excerpt(r, brand, competitors)
        if kind == "win" and len(wins) < win_cap:
            wins.append(ProofCard("win", r.platform, r.category, ex))
        elif kind == "loss" and len(losses) < loss_cap:
            losses.append(ProofCard("loss", r.platform, r.category, ex))
        if len(wins) >= win_cap and len(losses) >= loss_cap:
            break
    return wins + losses
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_proof_card_service.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/proof_card_service.py backend/tests/test_proof_card_service.py
git commit -m "feat(proof-cards): selection service for win/loss answer excerpts"
```

---

### Task 3: ClientViewProofCard schema + wire into /overview

**Files:**
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/client_view.py`
- Test: `backend/tests/test_api_client_view.py` (create if absent)

**Interfaces:**
- Consumes: `proof_card_service.select_proof_cards`; existing `_platform_label`; `Competitor` model.
- Produces: `ClientViewProofCard{ kind: str, platform_label: str, category: str, excerpt: str }`; `ClientViewOverview.proof_cards: list[ClientViewProofCard]` (default `[]`, populated for non-prospects only).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_client_view.py` (mirror existing client-view test setup; if the file does not exist, follow the fixture pattern in `backend/tests/test_api_scans.py` to seed a client, completed scan, and one `brand_detected=True` recommendation result with `response_text`):

```python
def test_overview_includes_proof_cards_for_client(http_client, seed_client_with_win_scan):
    token = seed_client_with_win_scan.share_token
    res = http_client.get(f"/api/v1/view/{token}/overview")
    assert res.status_code == 200
    body = res.json()
    assert "proof_cards" in body
    assert len(body["proof_cards"]) >= 1
    card = body["proof_cards"][0]
    assert card["kind"] in ("win", "loss")
    assert set(card.keys()) == {"kind", "platform_label", "category", "excerpt"}
    assert "response_text" not in card  # whitelist guard


def test_overview_proof_cards_empty_for_prospect(http_client, seed_prospect_with_win_scan):
    token = seed_prospect_with_win_scan.share_token
    body = http_client.get(f"/api/v1/view/{token}/overview").json()
    assert body["proof_cards"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_client_view.py -k proof_cards -v`
Expected: FAIL — `KeyError: 'proof_cards'` (field not yet on the schema).

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/client_view.py`, add after `ClientViewScore` (and update the module docstring's "Structurally excluded" list to keep `response_text` listed):

```python
class ClientViewProofCard(BaseModel):
    """One verbatim AI answer reduced to a single client-safe sentence. The
    excerpt is competitor-redacted and never contains raw response_text."""
    kind: str            # "win" | "loss"
    platform_label: str
    category: str
    excerpt: str
```

Add the field to `ClientViewOverview` (alongside the other optional sections):

```python
    proof_cards: list[ClientViewProofCard] = []
```

- [ ] **Step 4: Wire into the /overview endpoint**

In `backend/app/api/v1/client_view.py`:

Add imports:

```python
from app.models.competitor import Competitor
from app.schemas.client_view import ClientViewProofCard
from app.services.proof_card_service import select_proof_cards
```

Inside `get_overview`, before the `return ClientViewOverview(...)`, add:

```python
    # Verbatim proof cards (non-prospects only) — built from the latest completed
    # scan's client-owned results. Compute-on-read; response_text stays server-side.
    proof_cards: list[ClientViewProofCard] = []
    if not client.is_prospect:
        latest_scan = (
            db.query(Scan)
            .filter(Scan.client_id == client.id, Scan.status == "completed")
            .order_by(desc(Scan.completed_at))
            .first()
        )
        if latest_scan:
            scan_results = (
                db.query(ScanQueryResult)
                .filter(
                    ScanQueryResult.scan_id == latest_scan.id,
                    ScanQueryResult.competitor_id.is_(None),
                    ScanQueryResult.hallucination_flagged.is_(False),
                )
                .all()
            )
            competitor_names = [
                c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
            ]
            proof_cards = [
                ClientViewProofCard(
                    kind=pc.kind,
                    platform_label=_platform_label(pc.platform),
                    category=pc.category,
                    excerpt=pc.excerpt,
                )
                for pc in select_proof_cards(scan_results, client.name, competitor_names)
            ]
```

Add `proof_cards=proof_cards,` to the `ClientViewOverview(...)` constructor call.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_client_view.py -k proof_cards -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/tests/test_api_client_view.py
git commit -m "feat(client-view): proof cards on overview endpoint"
```

---

### Task 4: Per-result excerpt on /scan

**Files:**
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/client_view.py`
- Test: `backend/tests/test_api_client_view.py`

**Interfaces:**
- Consumes: `proof_card_service.result_excerpt`; existing `Competitor` query in this module.
- Produces: `ClientViewScanResult.excerpt: str | None = None` and `ClientViewScanResult.excerpt_kind: str | None = None`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_client_view.py`:

```python
def test_scan_result_carries_excerpt(http_client, seed_client_with_win_scan):
    token = seed_client_with_win_scan.share_token
    body = http_client.get(f"/api/v1/view/{token}/scan").json()
    seen = [r for r in body["results"] if r["seen_by_ai"]]
    assert seen and seen[0]["excerpt"]
    assert seen[0]["excerpt_kind"] in ("win", "loss")
    assert "response_text" not in seen[0]  # whitelist guard
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_client_view.py -k carries_excerpt -v`
Expected: FAIL — `KeyError: 'excerpt'`.

- [ ] **Step 3: Add schema fields**

In `backend/app/schemas/client_view.py`, add to `ClientViewScanResult`:

```python
    excerpt: str | None = None
    excerpt_kind: str | None = None  # "win" | "loss" | None
```

- [ ] **Step 4: Wire into the /scan endpoint**

In `backend/app/api/v1/client_view.py`, add import:

```python
from app.services.proof_card_service import result_excerpt
```

(Combine with the Task 3 import line if both are present.) Then in `get_scan`, after `results = (...).all()` and before the `return`, build the competitor list and per-row excerpts:

```python
    competitor_names = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
```

Replace the `ClientViewScanResult(...)` list comprehension body so each row computes its excerpt:

```python
    view_results = []
    for r in results:
        kind, excerpt = result_excerpt(r, client.name, competitor_names)
        view_results.append(
            ClientViewScanResult(
                platform_label=_platform_label(r.platform),
                category=r.category,
                query_text=r.query_text,
                seen_by_ai=r.brand_detected,
                ai_search_ranking=r.recommendation_position,
                excerpt=excerpt,
                excerpt_kind=kind,
            )
        )
    return ClientViewScan(completed_at=latest_scan.completed_at, results=view_results)
```

(Ensure `Competitor` is imported — added in Task 3; if Task 4 is done first, add the import here.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_client_view.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/tests/test_api_client_view.py
git commit -m "feat(client-view): per-result answer excerpt on scan endpoint"
```

---

### Task 5: Frontend types + ProofCardList on overview

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/components/view/ProofCardList.tsx`
- Modify: `frontend/src/app/view/[token]/page.tsx`

**Interfaces:**
- Consumes: overview payload from `getViewOverview` (now includes `proof_cards`).
- Produces: `ProofCardList` React component; `ClientViewProofCard` type; `proof_cards` on the overview type.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, add the interface and extend the existing client-view overview interface (locate the interface used by `getViewOverview` — it has fields like `change_narrative`, `traffic_value`):

```ts
export interface ClientViewProofCard {
  kind: "win" | "loss"
  platform_label: string
  category: string
  excerpt: string
}
```

Append to the overview interface:

```ts
  proof_cards?: ClientViewProofCard[]
```

Append to the scan-result interface (the one with `query_text`, `seen_by_ai`, `ai_search_ranking`):

```ts
  excerpt?: string | null
  excerpt_kind?: "win" | "loss" | null
```

- [ ] **Step 2: Create the ProofCardList component**

Create `frontend/src/components/view/ProofCardList.tsx`:

```tsx
// frontend/src/components/view/ProofCardList.tsx
// Verbatim, client-safe AI answer cards. Wins are flattering proof ("here's
// what ChatGPT said about you"); losses are honest opportunity ("a competitor
// was recommended, not you"). Excerpts are competitor-redacted server-side;
// raw responses never reach this surface.
import { Quote } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ClientViewProofCard } from "@/types"

function cardHeader(card: ClientViewProofCard): string {
  return card.kind === "win"
    ? `What ${card.platform_label} said about you`
    : `${card.platform_label} recommended a competitor — you weren't mentioned`
}

export function ProofCardList({ cards }: { cards: ClientViewProofCard[] }) {
  if (!cards || cards.length === 0) return null
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Straight From AI Search
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {cards.map((card, i) => {
          const isWin = card.kind === "win"
          return (
            <div
              key={`${card.platform_label}-${i}`}
              className={cn(
                "rounded-lg border bg-card p-4",
                isWin ? "border-score-strong/30" : "border-score-watch/30",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full border bg-muted/30 px-2.5 py-0.5 text-xs font-medium">
                  {card.platform_label}
                </span>
                <span
                  className={cn(
                    "text-xs font-semibold",
                    isWin ? "text-score-strong" : "text-score-watch",
                  )}
                >
                  {isWin ? "Seen by AI" : "Opportunity"}
                </span>
              </div>
              <p className="mt-2 text-sm font-medium text-foreground">{cardHeader(card)}</p>
              <div className="mt-2 flex gap-2">
                <Quote className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <p className="text-sm italic leading-relaxed text-muted-foreground">
                  &ldquo;{card.excerpt}&rdquo;
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Place it on the overview page**

In `frontend/src/app/view/[token]/page.tsx`:

Add the import with the other view-component imports:

```tsx
import { ProofCardList } from "@/components/view/ProofCardList"
```

Insert the component immediately AFTER the "What Changed" block (the `overview.change_narrative` block) and BEFORE the `AiPipelineValueCard` block:

```tsx
      {/* 2.25 Straight from AI — verbatim proof (clients only) */}
      {!isProspect && overview.proof_cards && overview.proof_cards.length > 0 && (
        <ProofCardList cards={overview.proof_cards} />
      )}
```

- [ ] **Step 4: Verify (type-check + build)**

Run: `cd frontend && npm run build`
Expected: build succeeds, no TypeScript errors. Confirm `ProofCardList` is referenced and `ClientViewProofCard` resolves.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/view/ProofCardList.tsx frontend/src/app/view/[token]/page.tsx
git commit -m "feat(client-view): proof card list on overview"
```

---

### Task 6: Inline "See what AI said" on the scan page

**Files:**
- Modify: `frontend/src/app/view/[token]/scan/page.tsx`

**Interfaces:**
- Consumes: scan payload results, now carrying `excerpt` / `excerpt_kind`.

- [ ] **Step 1: Render the excerpt disclosure**

In `frontend/src/app/view/[token]/scan/page.tsx`:

Update the file header comment (lines 1-3) to:

```tsx
// frontend/src/app/view/[token]/scan/page.tsx
// Read-only scan results: what AI was asked, whether the client was seen, and a
// curated, competitor-redacted excerpt of the answer. Raw AI responses are
// never available on this surface.
```

Inside the `results.map(...)` row, after the closing `</div>` of the badges block (the `flex shrink-0 items-center gap-2` div) and before the row's outer closing `</div>`, add a native `<details>` disclosure (server component friendly — no client JS needed):

```tsx
                {r.excerpt && (
                  <details className="mt-1 w-full">
                    <summary className="cursor-pointer text-xs font-medium text-primary hover:underline">
                      See what AI said
                    </summary>
                    <p className="mt-2 border-l-2 border-muted pl-3 text-sm italic leading-relaxed text-muted-foreground">
                      &ldquo;{r.excerpt}&rdquo;
                    </p>
                  </details>
                )}
```

Note: because the excerpt sits below the row content, change the row's outer wrapper so the details span full width — the existing `sm:flex-row sm:items-center sm:justify-between` becomes a column wrapper containing (a) the existing flex row of query+badges and (b) the details. Wrap the existing query `<div>` and badges `<div>` in a single `<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">`, and put the `<details>` as a sibling after it inside the outer `rounded-lg border bg-card p-4` container (make the outer container `flex flex-col gap-2`).

- [ ] **Step 2: Verify (type-check + build)**

Run: `cd frontend && npm run build`
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Run the app, open a client view `/view/<token>/scan` for a client with a completed scan, confirm rows where the client is seen show a "See what AI said" toggle revealing the quoted excerpt, and that no rival name appears (redacted to "a competitor").

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/view/[token]/scan/page.tsx
git commit -m "feat(client-view): inline answer excerpt on scan results"
```

---

## Self-Review

**Spec coverage:**
- Section 1 (selection + loss extractor) → Tasks 1, 2. ✓
- Section 2 (schema + API, no new endpoint) → Tasks 3, 4. ✓
- Section 3 (overview hero placement + scan disclosure, live HTML, tokens, language) → Tasks 5, 6. ✓
- Wins + losses scope → Task 1 (loss extractor), Task 2 (`_LOSS_CATEGORIES`, caps). ✓
- Compliance (no `response_text` on client surface) → asserted in Tasks 3 & 4 tests; `ProofCard` has no response_text (Task 2 test). ✓
- 2 wins + 1 loss cap, recommendation/local-only losses → Task 2 defaults + `_LOSS_CATEGORIES`. ✓

**Placeholder scan:** No TBD/TODO; all code blocks complete. Frontend type field names (`proof_cards`, `excerpt`, `excerpt_kind`) match backend schema exactly.

**Type consistency:** `ProofCard{kind,platform,category,excerpt}` (service, raw platform) → API maps `platform`→`platform_label` → `ClientViewProofCard{kind,platform_label,category,excerpt}` → TS `ClientViewProofCard` identical. `result_excerpt` returns `(kind, excerpt)` consumed identically in Tasks 3/4. Consistent.
