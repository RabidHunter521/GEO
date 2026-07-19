# Retention Narrative Fixes (Spec 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the flat-score weekly digest tip client-specific (deterministic ladder, no LLM) and render the already-served `headline_battle` on the client-view competitors page.

**Architecture:** A new `digest_tip_service.select_digest_tip` provides a data-grounded fallback tip that `claude_action.get_digest_action` uses instead of the band-keyed static tip; the frontend adds the missing battle card to `/view/[token]/competitors` consuming a field the API already returns.

**Tech Stack:** FastAPI service layer + pytest (SQLite in-memory `db` fixture); Next.js 15 server component + existing shadcn card idioms.

**Spec:** `docs/superpowers/specs/2026-07-19-retention-narrative-fixes-design.md`

## Global Constraints

- Zero new LLM calls; the ±5pt Claude gate in `claude_action.get_digest_action` is unchanged.
- No DB migration; no API schema change (the competitors payload already carries `headline_battle`).
- Client-facing language per CLAUDE.md §2 ("Seen by AI", "visibility frequency"; never "cited"/"mentioned").
- Every interpolated value in email HTML is `html.escape`-d.
- No tip rung may state a specific unless the underlying data exists (no invented evidence).
- Branch: `feat/retention-narrative-fixes` off master. Backend tests: `cd backend && python -m pytest <file> -v`.

---

### Task 1: `select_digest_tip` — deterministic tip ladder

**Files:**
- Create: `backend/app/services/digest_tip_service.py`
- Test: `backend/tests/test_digest_tip.py`

**Interfaces:**
- Consumes: `HeadlineBattle` dataclass from `app/services/headline_battle_service.py` (fields: `rival_name: str, query_text: str, platform_label: str, category: str, move_title: str | None, move_angle: str | None`); `DIGEST_STATIC_TIPS` from `app/core/constants.py`; `get_score_band` from `app/services/scoring_service.py`.
- Produces: `select_digest_tip(client, headline_battle, current_ai_citability: float) -> str` — used by Task 2.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_digest_tip.py
import uuid
from app.models.client import Client
from app.services.headline_battle_service import HeadlineBattle
from app.services.digest_tip_service import select_digest_tip
from app.core.constants import DIGEST_STATIC_TIPS


def make_client(**over):
    defaults = dict(
        id=uuid.uuid4(), name="Klinik Aisyah", website="https://ka.my",
        industry="dental clinic", brand_authority_score=60,
        content_quality_score=70, technical_foundations_verified=True,
        structured_data_verified=True,
    )
    defaults.update(over)
    return Client(**defaults)


def battle(move=None):
    return HeadlineBattle(
        rival_name="Dr. Lim Dental", query_text="Best dental clinic in KL",
        platform_label="ChatGPT", category="recommendation",
        move_title=move, move_angle=None,
    )


def test_rung1_battle_tip_names_query_and_rival():
    tip = select_digest_tip(make_client(), battle(), 55.0)
    assert "Best dental clinic in KL" in tip
    assert "Dr. Lim Dental" in tip


def test_rung2_toolkit_tip_when_no_battle_and_llms_unverified():
    c = make_client(technical_foundations_verified=False)
    tip = select_digest_tip(c, None, 55.0)
    assert "llms.txt" in tip


def test_rung2_schema_tip_when_only_structured_data_unverified():
    c = make_client(structured_data_verified=False)
    tip = select_digest_tip(c, None, 55.0)
    assert "structured data" in tip.lower()


def test_rung3_weakest_dimension_when_no_battle_and_toolkit_verified():
    c = make_client(brand_authority_score=10)
    tip = select_digest_tip(c, None, 90.0)
    assert "review" in tip.lower() or "authority" in tip.lower() or "profile" in tip.lower()


def test_rung4_band_fallback_for_brand_new_client():
    # Everything verified, all dimensions equal-ish, no battle: rung 3 still
    # fires (there is always a weakest dimension when a score exists) — the band
    # fallback is reachable only when citability is None-like (no scan basis).
    tip = select_digest_tip(make_client(), None, None)
    assert tip in DIGEST_STATIC_TIPS.values()


def test_no_banned_vocabulary():
    for args in [(make_client(), battle(), 40.0), (make_client(technical_foundations_verified=False), None, 40.0)]:
        tip = select_digest_tip(*args)
        for banned in ("cited", "uncited", "citation rate", "ranking position", "visibility gap"):
            assert banned not in tip.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_digest_tip.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.digest_tip_service`

- [ ] **Step 3: Implement the ladder**

```python
# backend/app/services/digest_tip_service.py
"""Deterministic, client-specific fallback tip for the weekly digest.

Fires when the Claude action is gated off (< ±5pt AI-citability move) or fails.
Priority ladder — first rung whose data actually exists wins; no rung may state
a specific the data doesn't back (no invented evidence), and no LLM is called.
"""
from app.core.constants import DIGEST_STATIC_TIPS
from app.models.client import Client
from app.services.scoring_service import get_score_band

# Rung 3: one deterministic sentence per weakest dimension. Keys mirror the
# dimension naming in prompts/digest.py.
_DIMENSION_TIPS = {
    "brand authority": (
        "Your brand authority is your weakest area — a steady stream of Google "
        "reviews is the fastest public evidence AI models pick up on."
    ),
    "content quality": (
        "Your content quality is your weakest area — publishing one detailed "
        "service page that answers real patient questions moves it most."
    ),
}


def _battle_tip(battle) -> str:
    return (
        f'Your score held steady this week. The fastest path to moving it: '
        f'"{battle.query_text}" — {battle.rival_name} is currently the one '
        f'seen by AI there.'
    )


def select_digest_tip(client: Client, headline_battle, current_ai_citability: float | None) -> str:
    # Rung 1 — the client's live lost battle (already computed for the digest).
    if headline_battle is not None:
        return _battle_tip(headline_battle)

    # Rung 2 — unverified toolkit files, named specifically.
    if not client.technical_foundations_verified:
        return (
            "Your llms.txt isn't verified live yet — publishing it is the "
            "quickest visibility gain available this week."
        )
    if not client.structured_data_verified:
        return (
            "Your structured data (schema.json) isn't verified live yet — "
            "adding it helps AI models understand exactly what you offer."
        )

    # Rung 3 — weakest assisted dimension, deterministic template.
    if current_ai_citability is not None:
        dims = {
            "brand authority": float(client.brand_authority_score),
            "content quality": float(client.content_quality_score),
        }
        weakest = min(dims, key=dims.get)
        if dims[weakest] < current_ai_citability:
            return _DIMENSION_TIPS[weakest]
        # Citability itself is the weakest — the battle rung would normally
        # cover this; without one, fall through to the band tip.
        return DIGEST_STATIC_TIPS[get_score_band(current_ai_citability)[0]]

    # Rung 4 — band floor (no scan basis at all).
    return DIGEST_STATIC_TIPS[get_score_band(0.0)[0]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_digest_tip.py -v`
Expected: PASS (6 tests). If `test_rung4` fails on the `None` citability path, the ladder's rung-4 branch is wrong — fix the ladder, not the test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/digest_tip_service.py backend/tests/test_digest_tip.py
git commit -m "feat(digest): deterministic client-specific tip ladder"
```

---

### Task 2: Wire the ladder into the digest flow

**Files:**
- Modify: `backend/app/services/claude_action.py` (whole file is 56 lines; gate at lines 17–27)
- Modify: `backend/app/services/digest_service.py:160-216` (`_compute_digest_data` — move `select_headline_battle` above `get_digest_action`, pass fallback)
- Test: `backend/tests/test_digest_tip.py` (extend)

**Interfaces:**
- Consumes: `select_digest_tip` (Task 1); `select_headline_battle(client_id, db)` (existing).
- Produces: `get_digest_action(client, current_ai_citability, prev_ai_citability, db=None, fallback_tip=None) -> str` — new optional kwarg, defaulting to old behavior.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_digest_tip.py`:

```python
from unittest.mock import patch
from app.services.claude_action import get_digest_action


def test_get_digest_action_uses_fallback_tip_below_gate():
    c = make_client()
    tip = get_digest_action(c, 50.0, 48.0, fallback_tip="CUSTOM FALLBACK")
    assert tip == "CUSTOM FALLBACK"


def test_get_digest_action_static_floor_without_fallback():
    c = make_client()
    tip = get_digest_action(c, 50.0, 48.0)
    assert tip in DIGEST_STATIC_TIPS.values()


def test_get_digest_action_claude_failure_falls_to_fallback():
    c = make_client()
    with patch("app.services.claude_action._generate_claude_action", side_effect=RuntimeError):
        tip = get_digest_action(c, 50.0, 30.0, fallback_tip="CUSTOM FALLBACK")
    assert tip == "CUSTOM FALLBACK"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_digest_tip.py -v`
Expected: FAIL — `TypeError: get_digest_action() got an unexpected keyword argument 'fallback_tip'`

- [ ] **Step 3: Implement**

In `claude_action.py`, change `get_digest_action`:

```python
def get_digest_action(
    client: Client,
    current_ai_citability: float,
    prev_ai_citability: float | None,
    db: Session | None = None,
    fallback_tip: str | None = None,
) -> str:
    score_change = (
        abs(current_ai_citability - prev_ai_citability)
        if prev_ai_citability is not None
        else 0.0
    )
    if score_change >= 5.0:
        try:
            return _generate_claude_action(client, current_ai_citability, prev_ai_citability, db)
        except Exception:
            pass
    if fallback_tip:
        return fallback_tip
    return DIGEST_STATIC_TIPS[_score_band(current_ai_citability)]
```

In `digest_service._compute_digest_data`, move the battle up and pass the fallback. Currently (lines 161–163 then 200):

```python
    trend = _compute_trend(current_citability, prev_citability)
    is_first_seen = _detect_first_seen(seen_count, prev_scan, db)
    action_text = get_digest_action(client, current_citability, prev_citability)
```

becomes:

```python
    trend = _compute_trend(current_citability, prev_citability)
    is_first_seen = _detect_first_seen(seen_count, prev_scan, db)
    headline_battle = select_headline_battle(client.id, db)
    action_text = get_digest_action(
        client,
        current_citability,
        prev_citability,
        fallback_tip=select_digest_tip(client, headline_battle, current_citability),
    )
```

Delete the later duplicate `headline_battle = select_headline_battle(client.id, db)` (line 200). Add the import at the top of `digest_service.py`:

```python
from app.services.digest_tip_service import select_digest_tip
```

- [ ] **Step 4: Run the full backend digest-related suite**

Run: `cd backend && python -m pytest tests/test_digest_tip.py tests/ -k "digest" -v`
Expected: PASS, including pre-existing digest tests (the no-arg static behavior is preserved for callers that don't pass `fallback_tip`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/claude_action.py backend/app/services/digest_service.py backend/tests/test_digest_tip.py
git commit -m "feat(digest): flat-score tip is now client-specific via tip ladder"
```

---

### Task 3: Render `headline_battle` on the client-view competitors page

**Files:**
- Modify: `frontend/src/lib/view-api.ts` (or wherever the `getViewCompetitors` return type lives — grounding step below)
- Modify: `frontend/src/app/view/[token]/competitors/page.tsx` (insert battle card after the "winning competitors callout" section, lines 127–143)
- Types: `frontend/src/types/index.ts` if view types live there

**Interfaces:**
- Consumes: `GET /view/{token}/competitors` already returns `headline_battle: {rival_name, query_text, platform_label, category, move_title, move_angle} | null` (serialized in `backend/app/api/v1/client_view.py` ~436–476 — verified 2026-07-19).
- Produces: rendered card; no new API surface.

- [ ] **Step 1: Grounding — locate the frontend type**

Run: `cd frontend && grep -rn "your_visibility_frequency" src/ --include=*.ts --include=*.tsx`
The type containing that field is the competitors view payload type. Add to it:

```ts
export interface ViewHeadlineBattle {
  rival_name: string
  query_text: string
  platform_label: string
  category: string
  move_title: string | null
  move_angle: string | null
}
// on the competitors payload type:
headline_battle?: ViewHeadlineBattle | null
```

(`?` keeps older cached payloads null-safe.)

- [ ] **Step 2: Insert the battle card**

In `competitors/page.tsx`, directly after the winning-competitors callout `</section>` (after line 143), insert:

```tsx
      {/* The battle to win next */}
      {data.headline_battle && (
        <section
          className="reveal rounded-xl border border-score-watch/40 bg-score-watch-bg p-4"
          style={{ animationDelay: "105ms" }}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-score-watch">
            The battle to win next
          </p>
          <p className="mt-2 text-sm text-foreground">
            Your competitor{" "}
            <span className="font-semibold">{data.headline_battle.rival_name}</span>{" "}
            is winning &ldquo;{data.headline_battle.query_text}&rdquo; on{" "}
            {data.headline_battle.platform_label}.
          </p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {data.headline_battle.move_title ? (
              <>
                The one move to flip it:{" "}
                <span className="font-medium text-foreground">
                  {data.headline_battle.move_title}
                </span>
                {data.headline_battle.move_angle && (
                  <> — {data.headline_battle.move_angle}</>
                )}
              </>
            ) : (
              <>The play to flip it is being prepared.</>
            )}
          </p>
        </section>
      )}
```

Note: the degrade sentence must match the digest/PDF wording exactly ("The play to flip it is being prepared.") — it's the established copy (`digest_service.py:324`).

- [ ] **Step 3: Verify with lint + build**

Run: `cd frontend && rtk lint && rtk tsc --noEmit`
Expected: clean. Then start the dev stack (run-app skill) and load a share link for a seeded client with a lost battle (`backend/scripts/seed_demo_clients.py` data): the card renders between the callout and the per-competitor list; with no lost battles the card is absent.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/view/[token]/competitors/page.tsx frontend/src/lib/view-api.ts frontend/src/types/index.ts
git commit -m "feat(client-view): render the headline battle on competitors page"
```

---

### Task 4: Final verification gate

- [ ] Run the whole backend suite: `cd backend && python -m pytest -q` — no regressions.
- [ ] Run the seenby-verify skill checklist (definition of done) against both changes; browser-verify the digest by triggering a manual digest send for a flat-score seeded client and inspecting the email HTML for the battle-derived tip (no banned vocabulary, values escaped).
- [ ] Commit any fixes; open PR per superpowers:finishing-a-development-branch.

## Self-review notes (spec coverage)

- Spec Fix A ladder rungs 1–4 → Tasks 1–2. Rung-3 "weakest dimension" is
  restricted to the two assisted dimensions because toolkit rungs already cover
  the two verified dimensions and citability-weakest degrades to band tip —
  documented deviation from the spec's four-way dimension wording, same intent.
- Spec Fix B → Task 3, degrade copy identical across surfaces.
- No-LLM constraint → ladder is pure; `get_digest_action` gate untouched.
