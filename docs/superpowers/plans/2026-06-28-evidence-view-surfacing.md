# Evidence View Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the existing proof-card "receipts" engine into the weekly digest and the monthly PDF, and let private (inbox-delivered) surfaces name the winning competitor while public surfaces stay redacted.

**Architecture:** Redaction becomes an explicit parameter threaded from callers through `proof_card_service.select_proof_cards` into `snippet_service.build_loss_excerpt` (default `True` = redacted/safe). The digest raises its proof-card caps and renders a win+loss pair with the rival named; the monthly PDF gains a new "What AI said about you this month" proof section. The public client view is deliberately untouched (already shows redacted cards).

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, pytest, WeasyPrint (PDF), Pillow (existing PNG path, untouched).

## Global Constraints

- Language rules (CLAUDE.md §2): use "Seen by AI" / "Not seen by AI"; loss framing uses "your competitor X is winning here". Never surface confidence scores, char offsets, token counts, or raw API responses on any client surface.
- `ProofCard` carries only the finished redacted/named excerpt, never `response_text` — do not add `response_text` to any client-facing payload.
- Default `redact=True` / `redact_competitors=True` everywhere — only the digest and PDF callers opt into `False`.
- All free-text rendered into email/PDF HTML must be `html.escape`-d (XSS).
- No schema migrations, no new scan data, no new platforms. Read existing `scan_query_results`.
- Backend tests run from `backend/` with `pytest`.

---

### Task 1: Redaction-as-parameter in snippet_service and proof_card_service

**Files:**
- Modify: `backend/app/services/snippet_service.py` (`build_loss_excerpt`, `_redact`)
- Modify: `backend/app/services/proof_card_service.py` (`result_excerpt`, `select_proof_cards`)
- Test: `backend/tests/test_snippet_service.py`, `backend/tests/test_proof_card_service.py`

**Interfaces:**
- Produces:
  - `snippet_service.build_loss_excerpt(response_text: str, brand: str, competitors: list[str], redact: bool = True) -> str | None`
  - `proof_card_service.result_excerpt(result, brand: str, competitors: list[str], redact: bool = True) -> tuple[str | None, str | None]`
  - `proof_card_service.select_proof_cards(results, brand: str, competitors: list[str], win_cap: int = 2, loss_cap: int = 1, redact_competitors: bool = True) -> list[ProofCard]`
- `build_excerpt` (the WIN extractor) is NOT changed — a win card quotes the brand's own sentence; any competitor named there is still redacted for safety. Only the LOSS path becomes nameable.

- [ ] **Step 1: Write the failing test for named loss excerpt**

In `backend/tests/test_snippet_service.py`, add:

```python
def test_build_loss_excerpt_names_competitor_when_redact_false():
    response = "For dental care in KL, RivalCo is the most recommended clinic. They have great reviews."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"], redact=False)
    assert result == "For dental care in KL, RivalCo is the most recommended clinic."


def test_build_loss_excerpt_default_still_redacts():
    response = "For dental care in KL, RivalCo is the most recommended clinic."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result == "For dental care in KL, [a competitor] is the most recommended clinic."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_snippet_service.py::test_build_loss_excerpt_names_competitor_when_redact_false -v`
Expected: FAIL — `build_loss_excerpt() got an unexpected keyword argument 'redact'`.

- [ ] **Step 3: Add the `redact` parameter to `build_loss_excerpt`**

In `backend/app/services/snippet_service.py`, change the signature and the single redaction call. The function currently ends by calling `_redact(chosen.strip(), names)`; make that conditional:

```python
def build_loss_excerpt(
    response_text: str, brand: str, competitors: list[str], redact: bool = True
) -> str | None:
    """Sentence naming a competitor, shown only when the brand is ABSENT.

    When redact=True (default, public surfaces) the competitor name is replaced
    with '[a competitor]'. When redact=False (private owner comms — digest, PDF)
    the rival is named, because rivalry is the point on those surfaces. Returns
    None when the text is empty, the brand appears (a win, not a loss), no
    competitor is configured, or no competitor is named in the text."""
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
    chosen = chosen.strip()
    if redact:
        chosen = _redact(chosen, names)
    if len(chosen) > _MAX_EXCERPT_CHARS:
        chosen = chosen[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    return chosen
```

- [ ] **Step 4: Run the snippet tests to verify they pass**

Run: `cd backend && pytest tests/test_snippet_service.py -v`
Expected: PASS — both new tests and all existing redaction tests green.

- [ ] **Step 5: Write the failing test for proof-card passthrough**

In `backend/tests/test_proof_card_service.py`, add (use the same lightweight result stub the existing tests in that file use — match its fixture/namedtuple style; a result needs `brand_detected`, `category`, `response_text`, `platform`, `recommendation_position`):

```python
def test_select_proof_cards_names_competitor_when_redact_false():
    results = [
        _result(
            brand_detected=False,
            category="recommendation",
            response_text="In KL, RivalCo is the top recommended clinic.",
            platform="chatgpt",
            recommendation_position=None,
        ),
    ]
    cards = select_proof_cards(
        results, brand="Acme Dental", competitors=["RivalCo"], redact_competitors=False
    )
    assert len(cards) == 1
    assert cards[0].kind == "loss"
    assert "RivalCo" in cards[0].excerpt
    assert "[a competitor]" not in cards[0].excerpt


def test_select_proof_cards_default_redacts_competitor():
    results = [
        _result(
            brand_detected=False,
            category="recommendation",
            response_text="In KL, RivalCo is the top recommended clinic.",
            platform="chatgpt",
            recommendation_position=None,
        ),
    ]
    cards = select_proof_cards(results, brand="Acme Dental", competitors=["RivalCo"])
    assert cards[0].excerpt and "RivalCo" not in cards[0].excerpt
    assert "[a competitor]" in cards[0].excerpt
```

If `test_proof_card_service.py` has no `_result` helper, add one at the top of the file:

```python
from types import SimpleNamespace

def _result(**kw):
    kw.setdefault("hallucination_flagged", False)
    return SimpleNamespace(**kw)
```

- [ ] **Step 6: Run the proof-card tests to verify they fail**

Run: `cd backend && pytest tests/test_proof_card_service.py::test_select_proof_cards_names_competitor_when_redact_false -v`
Expected: FAIL — `select_proof_cards() got an unexpected keyword argument 'redact_competitors'`.

- [ ] **Step 7: Thread `redact` through `proof_card_service`**

In `backend/app/services/proof_card_service.py`, update both functions. `result_excerpt` only forwards the flag on the LOSS branch (the win branch already redacts inside `build_excerpt` and is left as-is):

```python
def result_excerpt(
    result, brand: str, competitors: list[str], redact: bool = True
) -> tuple[str | None, str | None]:
    """(kind, excerpt) for one client-owned result, or (None, None).

    redact controls only the loss path: True (default) hides the rival, False
    names it for private owner comms.
    """
    if result.brand_detected:
        ex = snippet_service.build_excerpt(result.response_text or "", brand, competitors)
        return ("win", ex) if ex else (None, None)
    if result.category in _LOSS_CATEGORIES:
        ex = snippet_service.build_loss_excerpt(
            result.response_text or "", brand, competitors, redact=redact
        )
        return ("loss", ex) if ex else (None, None)
    return (None, None)


def select_proof_cards(
    results,
    brand: str,
    competitors: list[str],
    win_cap: int = 2,
    loss_cap: int = 1,
    redact_competitors: bool = True,
) -> list[ProofCard]:
    """Best wins first, then the best loss, capped. Empty when nothing qualifies.

    redact_competitors=False names the rival on loss cards (private surfaces only).
    """
    wins: list[ProofCard] = []
    losses: list[ProofCard] = []
    for r in sorted(results, key=_sort_key):
        kind, ex = result_excerpt(r, brand, competitors, redact=redact_competitors)
        if kind == "win" and len(wins) < win_cap:
            wins.append(ProofCard("win", r.platform, r.category, ex))
        elif kind == "loss" and len(losses) < loss_cap:
            losses.append(ProofCard("loss", r.platform, r.category, ex))
        if len(wins) >= win_cap and len(losses) >= loss_cap:
            break
    return wins + losses
```

- [ ] **Step 8: Run the full service test files to verify green**

Run: `cd backend && pytest tests/test_proof_card_service.py tests/test_snippet_service.py -v`
Expected: PASS — new tests pass, existing tests unchanged. `client_view`'s default call still redacts (no signature change at its call site).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/snippet_service.py backend/app/services/proof_card_service.py backend/tests/test_snippet_service.py backend/tests/test_proof_card_service.py
git commit -m "feat(proof-cards): make competitor redaction a caller parameter"
```

---

### Task 2: Digest shows a named win+loss pair

**Files:**
- Modify: `backend/app/services/digest_service.py` (the `select_proof_cards` call ~L166-175; `DigestData`; `_build_email_html` proof block ~L241-255)
- Test: `backend/tests/test_digest_service.py` (create if absent)

**Interfaces:**
- Consumes: `select_proof_cards(..., win_cap, loss_cap, redact_competitors)` and `ProofCard(kind, platform, category, excerpt)` from Task 1.
- Produces: `DigestData` gains `proof_win: tuple[str, str] | None` and `proof_loss: tuple[str, str] | None`, each `(excerpt, platform_label)` or `None`. Replaces the old `proof_quote` / `proof_platform` scalars.

- [ ] **Step 1: Write the failing test for digest pair selection**

In `backend/tests/test_digest_service.py`, add a test on the HTML builder. Inspect the existing `DigestData` construction in `digest_service.py` for required fields and build a complete instance (fill the non-proof fields with simple valid values copied from the dataclass defaults):

```python
import html as _html
from app.services.digest_service import _build_email_html, DigestData
from app.models.client import Client


def _client():
    c = Client.__new__(Client)
    c.name = "Acme Dental"
    return c


def _data(**over):
    base = dict(
        seen_count=5, total_count=10,
        current_ai_citability=50.0, current_overall_score=60.0,
        prev_ai_citability=45.0, trend="up", is_first_seen=False,
        action_text="Keep publishing.",
        proof_win=("Acme Dental is widely recommended in KL.", "ChatGPT"),
        proof_loss=("In KL, Dr. Lim Dental is the top pick.", "ChatGPT"),
    )
    base.update(over)
    return DigestData(**base)


def test_digest_html_shows_named_loss_card():
    htmlout = _build_email_html(_client(), _data())
    assert "Dr. Lim Dental" in htmlout            # rival named (private surface)
    assert "Acme Dental is widely recommended" in htmlout  # win shown too


def test_digest_html_win_only_when_no_loss():
    htmlout = _build_email_html(_client(), _data(proof_loss=None))
    assert "Acme Dental is widely recommended" in htmlout
    assert "recommended instead" not in htmlout.lower()


def test_digest_html_no_proof_block_when_empty():
    htmlout = _build_email_html(_client(), _data(proof_win=None, proof_loss=None))
    assert "Straight from" not in htmlout
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_digest_service.py -v`
Expected: FAIL — `DigestData.__init__() got an unexpected keyword argument 'proof_win'`.

- [ ] **Step 3: Update `DigestData` fields**

In `backend/app/services/digest_service.py`, in the `DigestData` dataclass, remove `proof_quote: str | None` and `proof_platform: str | None` and add:

```python
    # (excerpt, platform_label) for the verbatim win / loss cards, or None.
    proof_win: tuple[str, str] | None = None
    proof_loss: tuple[str, str] | None = None
```

- [ ] **Step 4: Update the selection logic**

Replace the proof-card block (currently `win_cap=1, loss_cap=0` building `proof_quote`/`proof_platform`) with a named win+loss selection:

```python
    cards = select_proof_cards(
        [r for r in client_results if not r.hallucination_flagged],
        client.name,
        competitor_names,
        win_cap=1,
        loss_cap=1,
        redact_competitors=False,  # private inbox surface — name the rival
    )

    def _label(p: str) -> str:
        return PLATFORM_LABELS.get(p, p.title())

    proof_win = next(
        ((c.excerpt, _label(c.platform)) for c in cards if c.kind == "win"), None
    )
    proof_loss = next(
        ((c.excerpt, _label(c.platform)) for c in cards if c.kind == "loss"), None
    )
```

Then update the `DigestData(...)` return to pass `proof_win=proof_win, proof_loss=proof_loss` instead of the old two scalar fields.

- [ ] **Step 5: Update `_build_email_html` proof block**

Replace the existing `proof_block` (the single green quote box) with a win box plus, when present, an amber loss box. Keep the existing inline-style visual language; escape every interpolated value:

```python
    proof_block = ""
    if data.proof_win:
        win_quote, win_platform = data.proof_win
        proof_block += f"""
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                    padding:16px 20px;margin-bottom:12px;">
          <p style="margin:0 0 6px;font-size:12px;color:#15803d;font-weight:600;
                    text-transform:uppercase;letter-spacing:0.05em;">
            Straight from {html.escape(win_platform)}
          </p>
          <p style="margin:0;font-size:15px;color:#14532d;line-height:1.6;font-style:italic;">
            &ldquo;{html.escape(win_quote)}&rdquo;
          </p>
        </div>"""
    if data.proof_loss:
        loss_quote, loss_platform = data.proof_loss
        proof_block += f"""
        <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
                    padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 6px;font-size:12px;color:#b45309;font-weight:600;
                    text-transform:uppercase;letter-spacing:0.05em;">
            Who {html.escape(loss_platform)} recommended instead
          </p>
          <p style="margin:0;font-size:15px;color:#78350f;line-height:1.6;font-style:italic;">
            &ldquo;{html.escape(loss_quote)}&rdquo;
          </p>
        </div>"""
```

- [ ] **Step 6: Run the digest tests to verify they pass**

Run: `cd backend && pytest tests/test_digest_service.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 7: Run any pre-existing digest tests for regressions**

Run: `cd backend && pytest -k digest -v`
Expected: PASS. If an existing test referenced `proof_quote`/`proof_platform`, update it to the new `proof_win`/`proof_loss` fields (repeat the tuple shape `(excerpt, platform_label)`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/digest_service.py backend/tests/test_digest_service.py
git commit -m "feat(digest): show named win+loss proof pair in weekly email"
```

---

### Task 3: Monthly PDF "What AI said about you this month" proof section

**Files:**
- Modify: `backend/app/services/report_service.py` (`ReportData` ~L155-194; `_gather_report_data` ~L350-357 already loads `client_results`; `_build_report_html` ~L525)
- Test: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: `select_proof_cards(..., redact_competitors=False)` and `ProofCard` from Task 1.
- Produces: `ReportData.proof_cards: list[ProofCard]` (default empty). A new private helper `_build_proof_html(data: ReportData) -> str` returning a section string (empty string when no cards).

- [ ] **Step 1: Write the failing test for the PDF proof section**

In `backend/tests/test_report_service.py`, add a unit test on the HTML helper (avoids needing WeasyPrint native libs):

```python
from app.services.report_service import _build_proof_html, ReportData
from app.services.proof_card_service import ProofCard


def _proof_data(cards):
    d = ReportData.__new__(ReportData)
    d.proof_cards = cards
    return d


def test_proof_html_names_competitor_on_loss_card():
    cards = [
        ProofCard("win", "chatgpt", "recommendation", "Acme Dental is a top KL clinic."),
        ProofCard("loss", "perplexity", "local", "In KL, Dr. Lim Dental is recommended first."),
    ]
    out = _build_proof_html(_proof_data(cards))
    assert "Dr. Lim Dental" in out                  # named on private PDF
    assert "Acme Dental is a top KL clinic." in out
    assert "Seen by AI" in out                       # approved language


def test_proof_html_empty_when_no_cards():
    assert _build_proof_html(_proof_data([])) == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/test_report_service.py::test_proof_html_names_competitor_on_loss_card -v`
Expected: FAIL — `cannot import name '_build_proof_html'`.

- [ ] **Step 3: Add `proof_cards` to `ReportData`**

In `backend/app/services/report_service.py`, add to the `ReportData` dataclass (after `newly_lost_queries`):

```python
    # Verbatim AI proof cards for the latest scan (rival named — private PDF).
    proof_cards: list = field(default_factory=list)
```

- [ ] **Step 4: Populate `proof_cards` in `_gather_report_data`**

`_gather_report_data` already loads `client_results` (client-owned rows for `latest_scan`) and `competitors_orm`. After the competitor-summary loop, add:

```python
    from app.services.proof_card_service import select_proof_cards
    proof_cards = select_proof_cards(
        [r for r in client_results if not r.hallucination_flagged],
        client.name,
        [c.name for c in competitors_orm],
        win_cap=2,
        loss_cap=1,
        redact_competitors=False,  # private reviewed PDF — name the rival
    )
```

Then add `proof_cards=proof_cards,` to the `ReportData(...)` constructor call at the end of `_gather_report_data`.

- [ ] **Step 5: Add the `_build_proof_html` helper**

Add near the other `_build_*_html` helpers in `report_service.py`. Use approved language and escape every excerpt:

```python
def _build_proof_html(data: ReportData) -> str:
    """The verbatim 'Seen by AI' proof section for the PDF, or '' when empty.

    Loss cards name the rival — this is the private, admin-reviewed deliverable."""
    if not data.proof_cards:
        return ""
    rows = []
    for c in data.proof_cards:
        platform = html.escape(PLATFORM_LABELS.get(c.platform, c.platform.title()))
        quote = html.escape(c.excerpt)
        if c.kind == "win":
            rows.append(
                f'<div class="proof-card proof-win">'
                f'<div class="proof-tag proof-tag-win">Seen by AI · {platform}</div>'
                f'<p class="proof-quote">&ldquo;{quote}&rdquo;</p></div>'
            )
        else:
            rows.append(
                f'<div class="proof-card proof-loss">'
                f'<div class="proof-tag proof-tag-loss">Who {platform} recommended instead</div>'
                f'<p class="proof-quote">&ldquo;{quote}&rdquo;</p></div>'
            )
    return (
        '<h2 class="section-title">What AI said about you this month</h2>'
        + "".join(rows)
    )
```

Add matching CSS to the `_CSS` string (near the existing badge styles):

```css
.proof-card { border-radius: 8px; padding: 12px 16px; margin-bottom: 10px; }
.proof-win { background: #f0fdf4; border: 1px solid #bbf7d0; }
.proof-loss { background: #fffbeb; border: 1px solid #fde68a; }
.proof-tag { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
.proof-tag-win { color: #15803d; }
.proof-tag-loss { color: #b45309; }
.proof-quote { font-style: italic; margin: 0; font-size: 11pt; }
```

- [ ] **Step 6: Render the section in `_build_report_html`**

In `_build_report_html`, build the section and inject it into the returned HTML next to the change-narrative block (find where `data.change_narrative` is rendered and place the proof section immediately after it):

```python
    proof_section = _build_proof_html(data)
```

Insert `{proof_section}` into the HTML template string right after the change-narrative markup.

- [ ] **Step 7: Run the report tests to verify they pass**

Run: `cd backend && pytest tests/test_report_service.py -v`
Expected: PASS — new tests green, existing report tests unaffected.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_report_service.py
git commit -m "feat(report): add named 'Seen by AI' proof section to monthly PDF"
```

---

### Task 4: Full regression + language-rule sweep

**Files:**
- Test only: run the existing suites that touch these surfaces.

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS — all green. In particular `test_proof_card_service.py`, `test_snippet_service.py`, `test_digest_service.py`, `test_report_service.py`, `test_api_scans.py` (admin PNG, still win-only/redacted), and any `client_view` tests (overview cards still redacted by default).

- [ ] **Step 2: Confirm the public/admin defaults stayed redacted**

Run: `cd backend && pytest -k "client_view or scans" -v`
Expected: PASS — no test sees a real competitor name on the public client view or the admin PNG surface (default redaction unchanged).

- [ ] **Step 3: Language-rule grep on the changed files**

Run: `cd backend && grep -rnE "cited|uncited|citation rate|confidence score|char offset|token count" app/services/digest_service.py app/services/report_service.py app/services/proof_card_service.py app/services/snippet_service.py || echo "clean"`
Expected: `clean` (banned client-facing terms absent from the touched surfaces).

- [ ] **Step 4: Commit (if any test fixups were needed)**

```bash
git add -A
git commit -m "test: regression sweep for evidence view surfacing"
```

---

## Self-Review

**Spec coverage:**
- Redaction-as-parameter → Task 1 ✅
- Digest win+loss pair, rival named → Task 2 ✅
- Monthly PDF proof section, rival named → Task 3 ✅
- Public client view unchanged (redacted) → verified, no task needed; Task 4 step 2 guards it ✅
- Graceful one-card/zero-card degradation → Task 2 steps cover win-only and empty; `select_proof_cards` already returns `[]` cleanly ✅
- Approved language / no raw responses → Task 3 uses "Seen by AI"; Task 4 step 3 greps banned terms ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code; commands have expected output.

**Type consistency:** `redact` (snippet/result_excerpt) vs `redact_competitors` (select_proof_cards) are intentionally named to match the existing public signatures of each function. `ProofCard(kind, platform, category, excerpt)` used consistently. `proof_win`/`proof_loss` are `(excerpt, platform_label)` tuples in both the dataclass and the HTML builder. `ReportData.proof_cards` is `list[ProofCard]`.
