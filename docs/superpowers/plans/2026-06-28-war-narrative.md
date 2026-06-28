# War Narrative (Rung 3 — Headline Battle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a single "headline battle" — named rival, the lost query they're winning, and the one move to flip it — on the weekly digest, monthly PDF, and client-view competitors page.

**Architecture:** A new deterministic `headline_battle_service.select_headline_battle` reuses `win_loss_service.compute_win_loss` to pick the most important lost query, names the competitor winning the most lost battles, and reads the existing `ContentBrief` for the "one move" (no LLM call). Three surfaces render the battle; everything degrades when there's no battle or no brief.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Pydantic, pytest, WeasyPrint (PDF).

## Global Constraints

- Selection is deterministic and fires **zero LLM calls** in any path. `headline_battle_service` must NOT import or call `content_brief_service`.
- Rank lost entries by: category priority (`recommendation`=0, `local`=1, else 9), then primary-threat-present (battles containing the primary threat first), then `query_text` (deterministic tiebreak — `recommendation_position` is not on the `WinLossEntry` schema, so it is not used).
- Primary threat = the competitor appearing in the most `lost` entries; tie broken by name ascending.
- `select_headline_battle` returns `None` when there are no `lost` entries.
- `HeadlineBattle` carries no `response_text`; the struct holds only `rival_name, query_text, platform_label, category, move_title, move_angle`.
- "One move" reuses the existing brief (`entry.brief.title`/`.angle`); `move_title`/`move_angle` are `None` when no brief exists. Surfaces degrade: battle without a brief still names the battle and shows "the play to flip it is being prepared."
- Approved language only (CLAUDE.md §2): "Seen by AI"/"Not seen by AI", "Your competitors are winning here". Never "cited/uncited/citation rate/confidence score/char offset/token count". Never surface raw responses/internal fields.
- All interpolated values in email/PDF HTML are `html.escape`-d.
- `/view/competitors` naming is allowed (page already names rivals, non-prospect gated); no new redaction logic; the overview is NOT touched. No DB migration.
- Backend tests run from `backend/` with `pytest`.

---

### Task 1: `headline_battle_service.select_headline_battle`

**Files:**
- Create: `backend/app/services/headline_battle_service.py`
- Test: `backend/tests/test_headline_battle_service.py`

**Interfaces:**
- Consumes: `win_loss_service.compute_win_loss(client_id, db) -> WinLossResponse` (entries have `category, platform, query_text, competitors_seen, outcome, brief` where `brief` is a `ContentBriefResponse | None` with `.title`/`.angle`); `PLATFORM_LABELS`.
- Produces:
  - `HeadlineBattle` dataclass: `rival_name: str, query_text: str, platform_label: str, category: str, move_title: str | None, move_angle: str | None`
  - `select_headline_battle(client_id: uuid.UUID, db: Session) -> HeadlineBattle | None`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_headline_battle_service.py`. The tests patch `compute_win_loss` so no DB is needed. Build entry/brief stubs with `SimpleNamespace`:

```python
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.services.headline_battle_service import select_headline_battle, HeadlineBattle


def _entry(category, query, competitors_seen, outcome, platform="chatgpt", brief=None):
    return SimpleNamespace(
        category=category, query_text=query, competitors_seen=competitors_seen,
        outcome=outcome, platform=platform, brief=brief,
    )


def _wl(entries):
    return SimpleNamespace(entries=entries)


def _call(entries):
    with patch("app.services.headline_battle_service.compute_win_loss", return_value=_wl(entries)):
        return select_headline_battle(uuid.uuid4(), db=object())


def test_none_when_no_lost_entries():
    entries = [_entry("recommendation", "best clinic KL", [], "won")]
    assert _call(entries) is None


def test_picks_recommendation_over_local():
    entries = [
        _entry("local", "best dentist near me", ["RivalCo"], "lost"),
        _entry("recommendation", "best invisalign KL", ["RivalCo"], "lost"),
    ]
    b = _call(entries)
    assert b is not None
    assert b.query_text == "best invisalign KL"  # recommendation ranks first


def test_names_primary_threat_competitor():
    # RivalCo appears in 2 lost battles, OtherCo in 1 -> RivalCo is the primary threat.
    entries = [
        _entry("recommendation", "q1", ["OtherCo"], "lost"),
        _entry("recommendation", "q2", ["RivalCo"], "lost"),
        _entry("local", "q3", ["RivalCo"], "lost"),
    ]
    b = _call(entries)
    # primary-threat-present battles rank ahead; among recommendation, q2 has RivalCo.
    assert b.rival_name == "RivalCo"
    assert b.query_text == "q2"


def test_reuses_existing_brief_as_move():
    brief = SimpleNamespace(title="Win Invisalign in KL", angle="Cover pricing and clinics.")
    entries = [_entry("recommendation", "best invisalign KL", ["RivalCo"], "lost", brief=brief)]
    b = _call(entries)
    assert b.move_title == "Win Invisalign in KL"
    assert b.move_angle == "Cover pricing and clinics."


def test_move_none_when_no_brief():
    entries = [_entry("recommendation", "best invisalign KL", ["RivalCo"], "lost", brief=None)]
    b = _call(entries)
    assert b.move_title is None and b.move_angle is None


def test_platform_label_mapped():
    entries = [_entry("recommendation", "q", ["RivalCo"], "lost", platform="chatgpt")]
    b = _call(entries)
    assert b.platform_label  # mapped via PLATFORM_LABELS, non-empty
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_headline_battle_service.py -v`
Expected: FAIL — `No module named 'app.services.headline_battle_service'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/headline_battle_service.py`:

```python
"""Pick the single 'headline battle' — the most important lost query, the rival
winning it, and the one move (an existing content brief) to flip it.

Deterministic and LLM-free: reuses win_loss_service classification and reads any
brief that already exists. Never generates a brief (no content_brief_service
import) so it is safe to call from automated digest/report flows.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.services.win_loss_service import compute_win_loss

# recommendation/local are the only WIN_LOSS_CATEGORIES; rank recommendation first
# (highest buyer intent). Unknown categories sort last.
_CATEGORY_PRIORITY = {"recommendation": 0, "local": 1}
_UNKNOWN_CATEGORY_RANK = 9


@dataclass
class HeadlineBattle:
    rival_name: str
    query_text: str
    platform_label: str
    category: str
    move_title: str | None
    move_angle: str | None


def _primary_threat(lost_entries) -> str | None:
    """The competitor named in the most lost battles (tie broken by name)."""
    counts: dict[str, int] = {}
    for e in lost_entries:
        for name in e.competitors_seen:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _sort_key(entry, primary: str | None):
    cat_rank = _CATEGORY_PRIORITY.get(entry.category, _UNKNOWN_CATEGORY_RANK)
    has_primary = 0 if (primary and primary in entry.competitors_seen) else 1
    return (cat_rank, has_primary, entry.query_text)


def select_headline_battle(client_id: uuid.UUID, db: Session) -> HeadlineBattle | None:
    wl = compute_win_loss(client_id, db)
    lost = [e for e in wl.entries if e.outcome == "lost"]
    if not lost:
        return None
    primary = _primary_threat(lost)
    chosen = sorted(lost, key=lambda e: _sort_key(e, primary))[0]
    rival = (
        primary
        if (primary and primary in chosen.competitors_seen)
        else (chosen.competitors_seen[0] if chosen.competitors_seen else None)
    )
    if rival is None:
        return None  # a 'lost' outcome always has >=1 competitor; guard anyway
    brief = chosen.brief
    return HeadlineBattle(
        rival_name=rival,
        query_text=chosen.query_text,
        platform_label=PLATFORM_LABELS.get(chosen.platform, chosen.platform.title()),
        category=chosen.category,
        move_title=brief.title if brief else None,
        move_angle=brief.angle if brief else None,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && pytest tests/test_headline_battle_service.py -v`
Expected: PASS — all six tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/headline_battle_service.py backend/tests/test_headline_battle_service.py
git commit -m "feat(war-narrative): deterministic headline-battle selector"
```

---

### Task 2: Weekly digest shows the headline battle

**Files:**
- Modify: `backend/app/services/digest_service.py` (`DigestData`; `_compute_digest_data`; `_build_email_html`)
- Test: `backend/tests/test_digest_service.py`

**Interfaces:**
- Consumes: `select_headline_battle`, `HeadlineBattle` from Task 1.
- Produces: `DigestData` gains `headline_battle: HeadlineBattle | None = None`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_digest_service.py`, add (extend the existing `_make_digest_data()` helper to accept `headline_battle=None` and pass it through):

```python
from app.services.headline_battle_service import HeadlineBattle


def _battle(move_title="Win Invisalign in KL", move_angle="Cover pricing + clinics."):
    return HeadlineBattle(
        rival_name="Dr. Lim Dental", query_text="best invisalign KL",
        platform_label="ChatGPT", category="recommendation",
        move_title=move_title, move_angle=move_angle,
    )


def test_digest_html_shows_headline_battle_with_move():
    db = MagicMock(); client = _make_client(); db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data(); data.headline_battle = _battle()
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    html = captured["html_body"]
    assert "Dr. Lim Dental" in html
    assert "best invisalign KL" in html
    assert "Win Invisalign in KL" in html


def test_digest_html_battle_without_brief_shows_prepared_text():
    db = MagicMock(); client = _make_client(); db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data(); data.headline_battle = _battle(move_title=None, move_angle=None)
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    html = captured["html_body"]
    assert "Dr. Lim Dental" in html
    assert "being prepared" in html.lower()


def test_digest_html_no_battle_block_when_none():
    db = MagicMock(); client = _make_client(); db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data()  # headline_battle defaults None
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    assert "the one move to flip it" not in captured["html_body"].lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_digest_service.py -k headline -v`
Expected: FAIL — `DigestData.__init__` has no `headline_battle` (or the block isn't rendered).

- [ ] **Step 3: Add the field + import**

In `backend/app/services/digest_service.py`, add the import (alongside the other service imports):

```python
from app.services.headline_battle_service import select_headline_battle
```

Add to `DigestData` (after the money fields):

```python
    headline_battle: object | None = None  # HeadlineBattle | None
```

- [ ] **Step 4: Populate in `_compute_digest_data`**

Before the `return DigestData(...)`, add:

```python
    headline_battle = select_headline_battle(client.id, db)
```

Then add `headline_battle=headline_battle,` to the `DigestData(...)` constructor.

- [ ] **Step 5: Render in `_build_email_html`**

After the `money_block` assembly, add a battle block and interpolate `{battle_block}` directly after `{money_block}` in the body f-string:

```python
    battle_block = ""
    if data.headline_battle is not None:
        b = data.headline_battle
        if b.move_title:
            move_html = (
                f"The one move to flip it: <strong>{html.escape(b.move_title)}</strong>"
                + (f" — {html.escape(b.move_angle)}" if b.move_angle else "")
            )
        else:
            move_html = "The play to flip it is being prepared."
        battle_block = f"""
        <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;
                    padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 6px;font-size:12px;color:#b91c1c;font-weight:600;
                    text-transform:uppercase;letter-spacing:0.05em;">
            The battle to win next
          </p>
          <p style="margin:0;font-size:15px;color:#7f1d1d;line-height:1.6;">
            Your competitor <strong>{html.escape(b.rival_name)}</strong> is winning
            &ldquo;{html.escape(b.query_text)}&rdquo; on {html.escape(b.platform_label)}.
            {move_html}
          </p>
        </div>"""
```

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_digest_service.py -v`
Expected: PASS — new tests green, existing digest tests unaffected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/digest_service.py backend/tests/test_digest_service.py
git commit -m "feat(digest): add headline-battle block to weekly email"
```

---

### Task 3: Monthly PDF shows the headline battle

**Files:**
- Modify: `backend/app/services/report_service.py` (`ReportData`; `_gather_report_data`; `_build_report_html`)
- Test: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: `select_headline_battle`, `HeadlineBattle` from Task 1.
- Produces: `ReportData.headline_battle: object | None = None`; a new `_build_battle_html(data) -> str` helper.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_report_service.py`, add:

```python
def test_report_html_shows_headline_battle():
    from app.services.report_service import _build_report_html, ReportData
    from app.services.headline_battle_service import HeadlineBattle
    client = MagicMock(); client.name = "Acme Dental"
    data = _make_report_data()
    data.headline_battle = HeadlineBattle(
        rival_name="Dr. Lim Dental", query_text="best invisalign KL",
        platform_label="ChatGPT", category="recommendation",
        move_title="Win Invisalign in KL", move_angle="Cover pricing + clinics.",
    )
    out = _build_report_html(client, data)
    assert "Dr. Lim Dental" in out
    assert "best invisalign KL" in out
    assert "Win Invisalign in KL" in out


def test_report_html_no_battle_section_when_none():
    from app.services.report_service import _build_report_html
    client = MagicMock(); client.name = "Acme Dental"
    data = _make_report_data()
    data.headline_battle = None
    out = _build_report_html(client, data)
    assert "battle to win next" not in out.lower()
```

(If `_make_report_data()` is absent, build `ReportData` via the existing pattern used by other report-HTML tests and set `headline_battle` explicitly.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_report_service.py -k headline_battle -v`
Expected: FAIL — `ReportData` has no `headline_battle`.

- [ ] **Step 3: Add the field + import**

In `backend/app/services/report_service.py`, add to the imports:

```python
from app.services.headline_battle_service import select_headline_battle
```

Add to `ReportData` (after `value_at_risk`):

```python
    # The single 'battle to win next' (rival + lost query + one move), or None.
    headline_battle: object | None = None
```

- [ ] **Step 4: Populate in `_gather_report_data`**

After the `value_at_risk = estimate_value_at_risk(...)` line, add:

```python
    headline_battle = select_headline_battle(client.id, db)
```

Add `headline_battle=headline_battle,` to the `ReportData(...)` constructor.

- [ ] **Step 5: Add `_build_battle_html` and render it**

Add the helper near the other `_build_*_html` helpers:

```python
def _build_battle_html(data: ReportData) -> str:
    """The single 'battle to win next' section, or '' when there is no battle."""
    if data.headline_battle is None:
        return ""
    b = data.headline_battle
    if b.move_title:
        move = (
            f"<strong>The one move to flip it:</strong> {html.escape(b.move_title)}"
            + (f" — {html.escape(b.move_angle)}" if b.move_angle else "")
        )
    else:
        move = "The play to flip it is being prepared."
    return f"""
  <h2>The Battle To Win Next</h2>
  <div class="stat-box" style="background:#fef2f2;border-color:#fecaca;">
    <div class="stat-sub">
      Your competitor <strong>{html.escape(b.rival_name)}</strong> is winning
      &ldquo;{html.escape(b.query_text)}&rdquo; on {html.escape(b.platform_label)} —
      you are not seen by AI there yet. {move}
    </div>
  </div>"""
```

In `_build_report_html`, build the section and interpolate it into the returned HTML immediately after the traffic section (where `value_at_risk`/`traffic_section` is placed):

```python
    battle_section = _build_battle_html(data)
```

Insert `{battle_section}` into the HTML template right after `{traffic_section}`.

- [ ] **Step 6: Run to verify pass**

Run: `cd backend && pytest tests/test_report_service.py -v`
Expected: PASS — new tests green, existing report tests unaffected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_report_service.py
git commit -m "feat(report): add 'battle to win next' section to monthly PDF"
```

---

### Task 4: Client-view competitors page exposes the headline battle

**Files:**
- Modify: `backend/app/schemas/client_view.py` (`ClientViewCompetitors`, ~line 169; add `ClientViewHeadlineBattle`)
- Modify: `backend/app/api/v1/client_view.py` (`get_competitors`, ~line 421-456)
- Test: `backend/tests/test_api_client_view.py`

**Interfaces:**
- Consumes: `select_headline_battle`, `HeadlineBattle` from Task 1.
- Produces: `ClientViewHeadlineBattle` schema (`rival_name, query_text, platform_label, move_title, move_angle`); `ClientViewCompetitors.headline_battle: ClientViewHeadlineBattle | None = None`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_api_client_view.py`, add a test in the competitors-endpoint style the file already uses (build a client with a completed scan whose latest results include a `lost` recommendation query naming a competitor; hit `/view/{token}/competitors`):

```python
def test_competitors_includes_headline_battle(client_with_lost_recommendation):
    # fixture: a non-prospect client whose latest scan has a recommendation query
    # where the client is NOT seen but competitor "RivalCo" IS.
    resp = _get_competitors(client_with_lost_recommendation)
    hb = resp["headline_battle"]
    assert hb is not None
    assert hb["rival_name"] == "RivalCo"
    assert hb["query_text"]
```

If the file has no fixture producing a lost recommendation result, build it inline following the file's existing scan/result setup: a `Scan(status="completed")`, a client-owned `ScanQueryResult(category="recommendation", brand_detected=False, response_text="... RivalCo ...")`, and a `Competitor(name="RivalCo")`. (Patch `select_headline_battle` only if the file's pattern is to mock services; otherwise prefer the real DB path so the test exercises selection end to end.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_api_client_view.py -k headline_battle -v`
Expected: FAIL — `headline_battle` not in the competitors response.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/client_view.py`, add before `ClientViewCompetitors`:

```python
class ClientViewHeadlineBattle(BaseModel):
    rival_name: str
    query_text: str
    platform_label: str
    move_title: str | None = None
    move_angle: str | None = None
```

Add to `ClientViewCompetitors`:

```python
    headline_battle: ClientViewHeadlineBattle | None = None
```

- [ ] **Step 4: Populate in `get_competitors`**

In `backend/app/api/v1/client_view.py`, import the selector and schema:

```python
from app.services.headline_battle_service import select_headline_battle
from app.schemas.client_view import ClientViewHeadlineBattle  # add to the existing client_view schema import block
```

In `get_competitors`, before building the `ClientViewCompetitors(...)` response, compute:

```python
    battle = select_headline_battle(client.id, db)
    headline_battle = (
        ClientViewHeadlineBattle(
            rival_name=battle.rival_name,
            query_text=battle.query_text,
            platform_label=battle.platform_label,
            move_title=battle.move_title,
            move_angle=battle.move_angle,
        )
        if battle else None
    )
```

Add `headline_battle=headline_battle,` to the `ClientViewCompetitors(...)` constructor.

- [ ] **Step 5: Run to verify pass**

Run: `cd backend && pytest tests/test_api_client_view.py -v`
Expected: PASS — new test green, existing competitor tests unaffected.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/tests/test_api_client_view.py
git commit -m "feat(client-view): expose headline battle on competitors page"
```

---

### Task 5: Full regression + no-auto-LLM + language sweep

**Files:** test-only.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS — all green, including the new headline-battle tests across service/digest/report/client-view.

- [ ] **Step 2: Confirm no automated-flow Claude call**

Run: `cd backend && grep -n "content_brief_service\|anthropic_client\|messages.create" app/services/headline_battle_service.py || echo "clean"`
Expected: `clean` — the selector never generates a brief.

- [ ] **Step 3: Confirm graceful-degradation tests pass**

Run: `cd backend && pytest -k "headline_battle or headline" -v`
Expected: PASS — no-battle and no-brief paths covered in service, digest, report.

- [ ] **Step 4: Language-rule grep on touched surfaces**

Run: `cd backend && grep -rnE "cited|uncited|citation rate|confidence score|char offset|token count" app/services/headline_battle_service.py app/services/digest_service.py app/services/report_service.py app/api/v1/client_view.py app/schemas/client_view.py || echo "clean"`
Expected: `clean`.

- [ ] **Step 5: Commit (if any fixups were needed)**

```bash
git add -A
git commit -m "test: regression sweep for war narrative"
```

---

## Self-Review

**Spec coverage:**
- Deterministic selector + primary-threat + ranking + None-when-no-battle → Task 1 ✅
- Reuse brief / degrade to None move → Task 1 (struct) + rendered in Tasks 2-4 ✅
- Digest surface → Task 2 ✅
- PDF surface → Task 3 ✅
- `/view/competitors` surface → Task 4 ✅
- No automated-flow LLM call → Task 1 (no `content_brief_service` import) + Task 5 step 2 ✅
- Approved language / no `response_text` → Task 5 steps 2-4 + struct definition ✅
- No DB migration → confirmed; only Pydantic response + dataclass fields ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code; commands have expected output.

**Type consistency:** `HeadlineBattle(rival_name, query_text, platform_label, category, move_title, move_angle)` used identically across Tasks 2-4. `select_headline_battle(client_id, db)` signature consistent. `DigestData.headline_battle` / `ReportData.headline_battle` are `object | None` holding a `HeadlineBattle`; `ClientViewHeadlineBattle` (Pydantic) mirrors the struct minus `category`. The ranking tiebreak (`query_text`, not `recommendation_position`) is stated once in Global Constraints and used in Task 1.
