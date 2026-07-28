# Page Citability Engine + Content Deliverables — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score any page on a client's site 0–100 for AI-readability with Claude rewrite suggestions, and generate admin-reviewed content deliverables (FAQ pack, comparison page, glossary) exportable as Markdown — the content half of the GEO retainer.

**Architecture:** New `citability_service` runs 10 deterministic checks (score computed in Python, never by Claude) on a single fetched page, then one Claude call proposes ≤5 rewrites; each audit persists to `page_audits` for per-URL history. New `deliverable_service` builds one of three deliverable types from scan evidence via one Claude call each, persisting draft rows the admin edits and marks reviewed. New admin page `/clients/[id]/content-studio` hosts both; client view untouched.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic, BeautifulSoup via `url_safety.safe_get`, Claude (Haiku for suggestions, Sonnet/`MODEL_NARRATIVE` for publish-ready deliverables), Next.js 15 + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-07-11-page-citability-engine-design.md`

## Global Constraints

- **No score/dimension change.** Nothing writes to GEO scores; no SCORE_VERSION bump. Citability score is informational.
- **Claude never produces a number.** The 0–100 score is `sum` of earned check points in Python. Suggestions/deliverables are text only.
- **Language rules (CLAUDE.md §2)** on every client-facing string; every Claude output field passes through `language_sanitizer.sanitize_text` before persistence (suggestions and deliverables are handed to clients verbatim).
- **Points table (verbatim from spec):** answer_up_front 15, question_headings 15, faq_block 10, scannable_structure 10, paragraph_length 10, heading_density 10, definitions 5, freshness_signal 10, author_byline 5, word_count 10. Pass = full points, warn = half (`points // 2`), fail = 0.
- **URL validation:** same registrable domain as `client.website` (subdomains allowed) AND `is_safe_crawl_url`; off-domain/unsafe → 422, nothing fetched. No sitewide crawl — one URL per audit.
- **Re-audit inserts a new row** (per-URL history). **Regenerating a deliverable creates a new draft row** — never overwrites a reviewed one. `reviewed` only via explicit admin PATCH.
- **Comparison-page prompt rules:** never disparage the competitor, no invented facts/statistics, no superlatives about the client not in the client profile.
- **Cost tracking:** every Claude call through `record_llm_call` with service names exactly: `citability_suggestions`, `deliverable_faq_pack`, `deliverable_comparison_page`, `deliverable_glossary` — and registered in `app/prompts/registry.py`.
- **Admin-only** (bearer `require_api_key`) on every new route. Client view (`/view/*`) gets nothing.
- **CLAUDE.md §9 gets the `/content-studio` line in the same branch** (rule: don't add pages without updating it).
- **RLS enabled inline** in the migration for both new tables. Current single alembic head is `51b4eb5916db` — the new migration's `down_revision`.
- Frontend: shadcn/ui only; all fetches via `src/lib/api.ts`; types in `src/types/index.ts`; band colors via `src/lib/score-utils.ts` `getScoreColor` — never hardcoded.
- Backend commands (this machine): poetry at `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe`, run from `backend/`. ⚠️ `backend/.env` DATABASE_URL points at PROD Supabase — never run `alembic upgrade`/`current` during development; prod migration happens at release via seenby-release.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/page_audit.py` (new) | PageAudit row: url, score, checks, suggestions (+ suggestions_failed retry flag) |
| `backend/app/models/content_deliverable.py` (new) | ContentDeliverable row: type, body_md, draft/reviewed lifecycle |
| `backend/alembic/versions/<generated>_add_page_audits_and_deliverables.py` (new) | both tables, RLS on |
| `backend/app/services/citability_service.py` (new) | URL validation, fetch, 10 checks, score, Claude suggestions, persist |
| `backend/app/services/deliverable_service.py` (new) | evidence collection + Claude generation + draft persistence |
| `backend/app/prompts/citability.py` (new) | suggestions prompt, `SUGGESTIONS_VERSION` |
| `backend/app/prompts/deliverables.py` (new) | 3 prompt builders + versions |
| `backend/app/prompts/registry.py` | + 4 service entries |
| `backend/app/api/v1/citability.py`, `deliverables.py` (new) + `router.py` | routes |
| `backend/app/schemas/citability.py`, `deliverable.py` (new) | response schemas |
| `frontend/src/app/clients/[id]/content-studio/` (new) | page.tsx + PageAuditsSection.tsx + DeliverablesSection.tsx + actions.ts |
| `frontend/src/components/layout/Sidebar.tsx`, `CLAUDE.md` §9 | nav |
| content-gaps + content-roadmap clients | "Turn these into content →" link |

---

### Task 1: Models + migration

**Files:**
- Create: `backend/app/models/page_audit.py`
- Create: `backend/app/models/content_deliverable.py`
- Modify: `backend/tests/conftest.py:9` (model import list)
- Create: `backend/alembic/versions/<generated>_add_page_audits_and_deliverables.py`
- Test: `backend/tests/test_citability_models.py`

**Interfaces:**
- Produces: `PageAudit(id, client_id, url, score, checks: list, suggestions: list, suggestions_failed: bool, created_at)`; `ContentDeliverable(id, client_id, type, competitor_id, title, body_md, source_context: dict, status, generated_at, reviewed_at)`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_citability_models.py`:

```python
def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_page_audit_round_trip(db):
    from app.models.page_audit import PageAudit
    client = _make_client(db)
    audit = PageAudit(
        client_id=client.id,
        url="https://acme.com/services",
        score=72,
        checks=[{"id": "word_count", "label": "Page length", "status": "pass",
                 "detail": "About 800 words.", "points": 10}],
        suggestions=[{"section": "Intro", "issue": "Too long", "rewrite": "Shorter intro."}],
    )
    db.add(audit)
    db.commit()
    row = db.query(PageAudit).one()
    assert row.score == 72
    assert row.checks[0]["id"] == "word_count"
    assert row.suggestions[0]["section"] == "Intro"
    assert row.suggestions_failed is False
    assert row.created_at is not None


def test_content_deliverable_defaults(db):
    from app.models.content_deliverable import ContentDeliverable
    client = _make_client(db)
    d = ContentDeliverable(
        client_id=client.id, type="faq_pack",
        title="FAQ pack", body_md="# FAQ\n...", source_context={"scan_id": None},
    )
    db.add(d)
    db.commit()
    row = db.query(ContentDeliverable).one()
    assert row.status == "draft"
    assert row.competitor_id is None
    assert row.reviewed_at is None
    assert row.generated_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `poetry run pytest tests/test_citability_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.page_audit'`

- [ ] **Step 3: Create the models**

`backend/app/models/page_audit.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class PageAudit(Base):
    """One page-citability audit run for one URL.

    Re-auditing the same URL inserts a new row — per-URL history is the
    point ("was 45, now 78 after rewrite" is retainer proof; the Phase 5
    report reads it). Score is server-computed from the deterministic
    checks; Claude only ever contributes the rewrite suggestions. See
    docs/superpowers/specs/2026-07-11-page-citability-engine-design.md.
    """

    __tablename__ = "page_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # List of {"id","label","status","detail","points"} — points = earned.
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Claude items {"section","issue","rewrite"}, sanitized before persist.
    suggestions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # True when the Claude suggestions call failed — UI offers "Retry".
    suggestions_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

`backend/app/models/content_deliverable.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class ContentDeliverable(Base):
    """One generated content deliverable (faq_pack | comparison_page | glossary).

    Always born a draft; only an explicit admin PATCH marks it reviewed —
    only reviewed rows count as "delivered" in the Phase 5 report/work log.
    Regenerating creates a NEW draft row; reviewed rows are never
    overwritten. body_md is sanitized Claude output the admin edits.
    """

    __tablename__ = "content_deliverables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # comparison_page only. SET NULL: deleting a competitor keeps the draft.
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    # Evidence used (query ids / scan id) — admin-only, never client-facing.
    source_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

In `backend/tests/conftest.py` line 9, add `page_audit, content_deliverable` to the model import list (keep `# noqa: F401` at the end):

```python
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot, control_query, guarantee, site_audit, page_audit, content_deliverable  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_citability_models.py -q`
Expected: 2 passed

- [ ] **Step 5: Create the migration**

Run: `poetry run alembic revision -m "add page audits and deliverables"` (from `backend/`; this does not apply anything). Keep the generated revision ID; replace the file body with (substituting `<generated>`):

```python
"""add page audits and deliverables

Revision ID: <generated>
Revises: 51b4eb5916db
Create Date: <keep generated date>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '<generated>'
down_revision: Union[str, None] = '51b4eb5916db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "page_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("suggestions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("suggestions_failed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_audits_client_id", "page_audits", ["client_id"])
    op.execute("ALTER TABLE page_audits ENABLE ROW LEVEL SECURITY;")

    op.create_table(
        "content_deliverables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_deliverables_client_id", "content_deliverables", ["client_id"])
    op.execute("ALTER TABLE content_deliverables ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE content_deliverables DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_content_deliverables_client_id", table_name="content_deliverables")
    op.drop_table("content_deliverables")
    op.execute("ALTER TABLE page_audits DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_page_audits_client_id", table_name="page_audits")
    op.drop_table("page_audits")
```

- [ ] **Step 6: Verify the migration chain (seenby-migrations gate)**

```bash
poetry run alembic heads
```
Expected: exactly ONE head — the new revision ID.

```bash
grep -rn "^revision" alembic/versions/ | sort | uniq -d -f1
```
Expected: no output. Do NOT run `alembic upgrade` (prod DB in .env).

- [ ] **Step 7: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass (684+).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/page_audit.py backend/app/models/content_deliverable.py backend/tests/conftest.py backend/tests/test_citability_models.py backend/alembic/versions/
git commit -m "feat(citability): PageAudit + ContentDeliverable models + migration"
```

---

### Task 2: Deterministic citability checks

**Files:**
- Create: `backend/app/services/citability_service.py`
- Test: `backend/tests/test_citability_service.py`

**Interfaces:**
- Produces: `validate_audit_url(client_website: str, url: str) -> str | None` (normalized URL or None); `run_citability_checks(html: str) -> list[dict]` (exactly 10 dicts `{"id","label","status","detail","points"}`, statuses `pass|warn|fail`, points = EARNED); `compute_citability_score(checks) -> int` (sum of points); exceptions `OffDomainUrlError`, `PageFetchError`; `fetch_page(url) -> str` (html text, raises PageFetchError). Check ids in order: `answer_up_front, question_headings, faq_block, scannable_structure, paragraph_length, heading_density, definitions, freshness_signal, author_byline, word_count`.
- Consumes: `is_safe_crawl_url`, `safe_get` from `url_safety`; `_domain_base` from `verification_crawler`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_citability_service.py`:

```python
"""citability_service tests — deterministic checks against HTML fixtures (spec §8)."""
from unittest.mock import patch


def _para(sentences: int = 3) -> str:
    s = ("Our dentists explain every step in plain language so patients always "
         "know what to expect during a visit. ")
    return "<p>" + (s * sentences).strip() + "</p>"


# Passes all 10 checks: 24-word lead para with a definition before any H2,
# 5/6 question H2/H3s, FAQ heading, 1 table + 2 lists, ~48-word paragraphs,
# 6 headings over ~400 words, published_time meta, author meta + byline,
# 300-3000 words.
EXEMPLARY_HTML = f"""<html><head>
<meta name="author" content="Dr. Sarah Lim">
<meta property="article:published_time" content="2026-06-01T00:00:00Z">
</head><body><main>
<h1>Family Dental Care in Kuala Lumpur</h1>
<p>Acme Dental Clinic is a family dental clinic in Kuala Lumpur offering checkups,
braces, implants and emergency care with transparent pricing for every treatment.</p>
<h2>What services does Acme Dental offer?</h2>
{_para()}{_para()}
<h2>How much does a dental checkup cost?</h2>
<table><tr><th>Treatment</th><th>Price</th></tr>
<tr><td>Checkup</td><td>RM 120</td></tr></table>
{_para()}
<h2>Why do patients choose Acme Dental?</h2>
<ul><li>Gentle care</li><li>Transparent pricing</li></ul>
<ul><li>Weekend hours</li><li>Central location</li></ul>
{_para()}
<h2>Frequently Asked Questions</h2>
<h3>Do you accept walk-in patients?</h3>
{_para()}
<h3>Can I book online?</h3>
{_para()}
<p>Written by Dr. Sarah Lim, updated 1 June 2026.</p>
</main></body></html>"""

_WALL_SENTENCE = ("we care about long term dental health and we want every patient "
                  "to feel comfortable from the moment they arrive until the moment "
                  "they leave our clinic and we work hard to earn that trust. ")
# No headings, lists, tables, dates, bylines, or definition patterns —
# only word_count (10 pts) passes.
WALL_OF_TEXT_HTML = ("<html><body><main><p>" + _WALL_SENTENCE * 22 + "</p><p>"
                     + _WALL_SENTENCE * 18 + "</p></main></body></html>")


def _by_id(checks):
    return {c["id"]: c for c in checks}


# 1. Exemplary page scores >= 90.
def test_exemplary_page_scores_at_least_90():
    from app.services.citability_service import compute_citability_score, run_citability_checks
    checks = run_citability_checks(EXEMPLARY_HTML)
    assert len(checks) == 10
    assert compute_citability_score(checks) >= 90
    for c in checks:
        assert set(c) == {"id", "label", "status", "detail", "points"}


# 2. Wall of text: only word_count passes; score reflects the points table exactly.
def test_wall_of_text_scores_exactly_word_count_points():
    from app.services.citability_service import compute_citability_score, run_citability_checks
    checks = run_citability_checks(WALL_OF_TEXT_HTML)
    by = _by_id(checks)
    assert by["answer_up_front"]["status"] == "fail"
    assert by["paragraph_length"]["status"] == "fail"
    assert by["heading_density"]["status"] == "fail"
    assert by["word_count"]["status"] == "pass"
    assert compute_citability_score(checks) == 10


# 5. Warn earns half points.
def test_warn_earns_half_points():
    from app.services.citability_service import run_citability_checks
    # exactly one list, no table → scannable_structure warns (10 // 2 = 5)
    html = "<html><body><main><p>Short intro.</p><ul><li>One</li></ul></main></body></html>"
    c = _by_id(run_citability_checks(html))["scannable_structure"]
    assert c["status"] == "warn"
    assert c["points"] == 5


# 3. Off-domain / unsafe URLs rejected; subdomains allowed.
def test_validate_audit_url_domain_rules():
    from app.services import citability_service
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True):
        ok = citability_service.validate_audit_url("https://acme.com", "https://acme.com/services")
        sub = citability_service.validate_audit_url("https://acme.com", "https://blog.acme.com/post")
        www = citability_service.validate_audit_url("https://www.acme.com", "https://acme.com/x")
        off = citability_service.validate_audit_url("https://acme.com", "https://rival.com/page")
    assert ok == "https://acme.com/services"
    assert sub == "https://blog.acme.com/post"
    assert www == "https://acme.com/x"
    assert off is None


def test_validate_audit_url_unsafe_rejected():
    from app.services import citability_service
    with patch.object(citability_service, "is_safe_crawl_url", return_value=False):
        assert citability_service.validate_audit_url("https://acme.com", "https://acme.com/x") is None


def test_fetch_page_raises_on_non_html_or_error():
    import pytest
    from app.services import citability_service
    from app.services.citability_service import PageFetchError
    from app.services.url_safety import SafeResponse
    with patch.object(citability_service, "safe_get",
                      return_value=SafeResponse(404, "", {"content-type": "text/html"})):
        with pytest.raises(PageFetchError):
            citability_service.fetch_page("https://acme.com/missing")
    with patch.object(citability_service, "safe_get", side_effect=Exception("timeout")):
        with pytest.raises(PageFetchError):
            citability_service.fetch_page("https://acme.com/slow")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_citability_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.citability_service'`

- [ ] **Step 3: Implement the service**

`backend/app/services/citability_service.py` — complete file (Task 3 appends the Claude + persistence half):

```python
"""Page citability audit — deterministic AI-readability checks (spec §3).

The 0-100 score is a pure Python sum of earned check points; Claude never
produces the number (same rule as action_center impact). Check details are
plain English (CLAUDE.md §2) — they are shown to the admin and may be
handed to clients alongside the rewrite suggestions.
"""
import re
import statistics
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup

from app.services.url_safety import is_safe_crawl_url, safe_get
from app.services.verification_crawler import _domain_base

logger = structlog.get_logger()

_TIMEOUT = 10.0

_QUESTION_STARTERS = (
    "what", "how", "why", "when", "which", "who", "can", "should", "is", "are", "do", "does",
)
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")
_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:" + "|".join(_MONTHS) + r")\s+\d{4}\b"),
    re.compile(r"\b(?:" + "|".join(_MONTHS) + r")\s+\d{1,2},?\s+\d{4}\b"),
]
_DEFINITION_RE = re.compile(r"\b[A-Z][\w&' -]{0,60}\s+is\s+(?:a|an|the)\s+\w")
_BYLINE_RE = re.compile(r"\b[Bb]y\s+(?:Dr\.?\s+)?[A-Z][a-z]+")


class OffDomainUrlError(ValueError):
    """URL is not on the client's domain (or is unsafe) — nothing was fetched."""


class PageFetchError(RuntimeError):
    """The page could not be fetched or is not an HTML page."""


def validate_audit_url(client_website: str, url: str) -> str | None:
    """Normalized URL when on the client's registrable domain and safe; else None.

    Subdomains of the client domain are allowed (blog.acme.com for acme.com).
    """
    if "://" not in url:
        url = f"https://{url}"
    if not is_safe_crawl_url(url):
        return None
    client_host = urlparse(_domain_base(client_website)).netloc.lower().removeprefix("www.")
    url_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not client_host or not url_host:
        return None
    if url_host == client_host or url_host.endswith("." + client_host):
        return url
    return None


def fetch_page(url: str) -> str:
    """Fetch one HTML page. Raises PageFetchError on any failure —
    an audit with no page behind it is noise and must not persist."""
    try:
        r = safe_get(url, timeout=_TIMEOUT)
    except Exception as exc:
        raise PageFetchError(f"could not fetch {url}") from exc
    content_type = r.headers.get("content-type", "").lower()
    if r.status_code != 200 or ("html" not in content_type and content_type != ""):
        raise PageFetchError(f"{url} returned {r.status_code} ({content_type or 'no content type'})")
    return r.text


def _result(check_id: str, label: str, status: str, detail: str, max_points: int) -> dict:
    earned = max_points if status == "pass" else (max_points // 2 if status == "warn" else 0)
    return {"id": check_id, "label": label, "status": status, "detail": detail, "points": earned}


def _extract(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    # Chrome elements would pollute list/heading counts — drop them before
    # selecting the content root.
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup

    text = main.get_text(" ", strip=True)
    words = text.split()
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    h23 = [h.get_text(" ", strip=True) for h in main.find_all(["h2", "h3"])]
    all_heading_count = len(main.find_all(["h2", "h3", "h4"]))
    faq_headings = [
        h.get_text(" ", strip=True).lower() for h in main.find_all(["h1", "h2", "h3", "h4"])
    ]

    # First content element decides answer_up_front: is there a <p> before any <h2>?
    lead_para: str | None = None
    for el in main.find_all(["p", "h2"]):
        if el.name == "h2":
            break
        lead_para = el.get_text(" ", strip=True)
        if lead_para:
            break

    # Freshness sources beyond visible text: meta dates and <time datetime>.
    meta_date = False
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").lower()
        if key in ("article:published_time", "article:modified_time", "date",
                   "last-modified", "publish-date", "dc.date"):
            if (meta.get("content") or "").strip():
                meta_date = True
                break
    if not meta_date and soup.find("time", attrs={"datetime": True}):
        meta_date = True

    meta_author = False
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta and (author_meta.get("content") or "").strip():
        meta_author = True
    if not meta_author:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if '"author"' in (script.string or script.get_text() or ""):
                meta_author = True
                break

    return {
        "text": text,
        "words": words,
        "paragraphs": paragraphs,
        "h23": h23,
        "heading_count": all_heading_count,
        "faq_headings": faq_headings,
        "lead_para": lead_para,
        "tables": len(main.find_all("table")),
        "lists": len(main.find_all(["ul", "ol"])),
        "meta_date": meta_date,
        "meta_author": meta_author,
    }


def _is_question(heading: str) -> bool:
    lowered = heading.lower().strip()
    return lowered.endswith("?") or lowered.split(" ", 1)[0] in _QUESTION_STARTERS


def run_citability_checks(html: str) -> list[dict]:
    """Run the 10 deterministic checks. Always returns exactly 10 dicts."""
    x = _extract(html)
    checks: list[dict] = []

    # 1. answer_up_front (15) — first content paragraph <= 60 words, before any H2.
    lead = x["lead_para"]
    lead_words = len(lead.split()) if lead else 0
    if lead and lead_words <= 60:
        checks.append(_result(
            "answer_up_front", "Answer up front", "pass",
            f"The page opens with a {lead_words}-word summary before the first section.", 15))
    elif lead and lead_words <= 100:
        checks.append(_result(
            "answer_up_front", "Answer up front", "warn",
            f"The opening paragraph is {lead_words} words — trim it to 60 or fewer so AI "
            "assistants can quote it whole.", 15))
    else:
        checks.append(_result(
            "answer_up_front", "Answer up front", "fail",
            "The page doesn't open with a short summary paragraph — AI assistants favour "
            "pages that answer the question in the first 60 words.", 15))

    # 2. question_headings (15) — >= 25% of H2/H3s are question-form.
    if x["h23"]:
        ratio = sum(1 for h in x["h23"] if _is_question(h)) / len(x["h23"])
        if ratio >= 0.25:
            status = "pass"
            detail = f"{ratio:.0%} of section headings are written as questions."
        elif ratio >= 0.10:
            status = "warn"
            detail = (f"Only {ratio:.0%} of section headings are questions — aim for at "
                      "least a quarter, phrased the way a customer would ask.")
        else:
            status = "fail"
            detail = ("Section headings aren't phrased as questions — AI assistants match "
                      "headings to the questions people ask them.")
        checks.append(_result("question_headings", "Question-style headings", status, detail, 15))
    else:
        checks.append(_result(
            "question_headings", "Question-style headings", "fail",
            "The page has no section headings at all.", 15))

    # 3. faq_block (10) — FAQ heading, or >= 3 consecutive question headings.
    has_faq_heading = any("faq" in h or "frequently asked" in h for h in x["faq_headings"])
    consecutive = 0
    max_consecutive = 0
    for h in x["h23"]:
        consecutive = consecutive + 1 if _is_question(h) else 0
        max_consecutive = max(max_consecutive, consecutive)
    if has_faq_heading or max_consecutive >= 3:
        checks.append(_result(
            "faq_block", "FAQ section", "pass", "The page has a question-and-answer section.", 10))
    else:
        checks.append(_result(
            "faq_block", "FAQ section", "fail",
            "No FAQ section found — a short Q&A block is the easiest content for AI "
            "assistants to reuse.", 10))

    # 4. scannable_structure (10) — >= 1 table or >= 2 lists; exactly 1 list warns.
    if x["tables"] >= 1 or x["lists"] >= 2:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "pass",
            f"Found {x['tables']} table(s) and {x['lists']} list(s).", 10))
    elif x["lists"] == 1:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "warn",
            "Only one list on the page — add a comparison table or another list to make "
            "key facts scannable.", 10))
    else:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "fail",
            "No tables or lists — AI assistants extract facts most reliably from "
            "structured elements.", 10))

    # 5. paragraph_length (10) — median paragraph <= 80 words.
    if x["paragraphs"]:
        median = statistics.median(len(p.split()) for p in x["paragraphs"])
        if median <= 80:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "pass",
                f"Median paragraph is {median:.0f} words.", 10))
        elif median <= 120:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "warn",
                f"Median paragraph is {median:.0f} words — break paragraphs up so each "
                "makes one point.", 10))
        else:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "fail",
                f"Median paragraph is {median:.0f} words — walls of text are hard for AI "
                "assistants to quote accurately.", 10))
    else:
        checks.append(_result(
            "paragraph_length", "Paragraph length", "fail",
            "No paragraphs found on the page.", 10))

    # 6. heading_density (10) — >= 1 heading per 300 words.
    word_count = len(x["words"])
    if word_count and x["heading_count"] >= word_count / 300:
        checks.append(_result(
            "heading_density", "Heading coverage", "pass",
            f"{x['heading_count']} headings across {word_count} words.", 10))
    elif word_count and x["heading_count"] >= word_count / 500:
        checks.append(_result(
            "heading_density", "Heading coverage", "warn",
            "Sections run long between headings — aim for a heading roughly every 300 "
            "words.", 10))
    else:
        checks.append(_result(
            "heading_density", "Heading coverage", "fail",
            "Too few headings for the amount of text — AI assistants navigate pages by "
            "their headings.", 10))

    # 7. definitions (5) — an "X is a/an/the …" sentence in the first half.
    first_half = x["text"][: len(x["text"]) // 2]
    if _DEFINITION_RE.search(first_half):
        checks.append(_result(
            "definitions", "Plain definition", "pass",
            "The page defines its subject in plain terms early on.", 5))
    else:
        checks.append(_result(
            "definitions", "Plain definition", "fail",
            'Add an early sentence in the form "X is a …" — definition sentences are '
            "quoted verbatim by AI assistants.", 5))

    # 8. freshness_signal (10) — a parseable date in meta or page text.
    text_date = any(p.search(x["text"]) for p in _DATE_PATTERNS)
    if x["meta_date"] or text_date:
        checks.append(_result(
            "freshness_signal", "Freshness signal", "pass",
            "The page carries a published or updated date.", 10))
    else:
        checks.append(_result(
            "freshness_signal", "Freshness signal", "fail",
            "No visible date — AI assistants prefer content they can tell is current.", 10))

    # 9. author_byline (5) — byline pattern or author meta/JSON-LD.
    if x["meta_author"] or _BYLINE_RE.search(x["text"]):
        checks.append(_result(
            "author_byline", "Author byline", "pass",
            "The page names its author.", 5))
    else:
        checks.append(_result(
            "author_byline", "Author byline", "fail",
            "No author on the page — a named author is a trust signal AI assistants "
            "weigh.", 5))

    # 10. word_count (10) — 300-3000 words; thin or bloated both warn.
    if 300 <= word_count <= 3000:
        checks.append(_result(
            "word_count", "Page length", "pass", f"About {word_count} words.", 10))
    elif 150 <= word_count < 300 or 3000 < word_count <= 5000:
        checks.append(_result(
            "word_count", "Page length", "warn",
            f"About {word_count} words — aim for 300-3,000 words of focused content.", 10))
    else:
        checks.append(_result(
            "word_count", "Page length", "fail",
            f"About {word_count} words — far outside the 300-3,000 word range AI "
            "assistants favour.", 10))

    return checks


def compute_citability_score(checks: list[dict]) -> int:
    """0-100, server-computed. points fields already hold EARNED points."""
    return sum(c["points"] for c in checks)
```

Implementation note: `WALL_OF_TEXT_HTML`'s word_count is ~1080 (pass, full 10 points); every other check fails, so the exact-score assertion is `== 10`. If the exemplary fixture misses 100, the `>= 90` assertion still holds — but investigate any check that isn't `pass` on it before accepting.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_citability_service.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/citability_service.py backend/tests/test_citability_service.py
git commit -m "feat(citability): 10 deterministic checks + server-computed 0-100 score"
```

---

### Task 3: Claude suggestions + audit persistence

**Files:**
- Create: `backend/app/prompts/citability.py`
- Modify: `backend/app/services/citability_service.py` (append)
- Modify: `backend/app/prompts/registry.py`
- Test: `backend/tests/test_citability_service.py` (append)

**Interfaces:**
- Produces: `audit_page(client: Client, url: str, db: Session) -> PageAudit` (validates internally — raises `OffDomainUrlError` / `PageFetchError`; persists + ActivityLog `page_audit_run`); `generate_suggestions(client, checks, page_text, db) -> tuple[list[dict], bool]` (`(items, failed)`); `build_citability_suggestions(client, problem_checks, excerpt) -> str` prompt; `SUGGESTIONS_VERSION = "v1"`; registry entry `citability_suggestions` on `MODEL`.
- Consumes: Task 2's checks/score/fetch/validate; `anthropic_client`, `MODEL`, `strip_code_fences` from `claude_client`; `record_llm_call`; `sanitize_text` from `language_sanitizer`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_citability_service.py`:

```python
def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _mock_anthropic(text: str):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    return ac


_SUGGESTIONS_JSON = ('{"suggestions": [{"section": "Intro", "issue": "No summary up front", '
                     '"rewrite": "Acme Dental is a family dental clinic in KL."}]}')


def test_audit_page_persists_with_suggestions(db):
    from app.models.activity_log import ActivityLog
    from app.services import citability_service
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client",
                      return_value=_mock_anthropic(_SUGGESTIONS_JSON)), \
         patch.object(citability_service, "record_llm_call"):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    assert audit.score == 10
    assert audit.url == "https://acme.com/about"
    assert audit.suggestions_failed is False
    assert audit.suggestions[0]["section"] == "Intro"
    log = db.query(ActivityLog).filter(ActivityLog.client_id == client.id).one()
    assert log.event_type == "page_audit_run"


def test_claude_failure_persists_audit_with_empty_suggestions(db):
    from app.services import citability_service
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client", side_effect=Exception("api down")):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    assert audit.score == 10
    assert audit.suggestions == []
    assert audit.suggestions_failed is True


def test_suggestions_are_sanitized(db):
    from app.services import citability_service
    client = _make_client(db)
    dirty = ('{"suggestions": [{"section": "Intro", "issue": "Not cited by AI", '
             '"rewrite": "Get mentioned more often."}]}')
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client",
                      return_value=_mock_anthropic(dirty)), \
         patch.object(citability_service, "record_llm_call"):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    joined = " ".join(f"{s['issue']} {s['rewrite']}" for s in audit.suggestions)
    assert "cited" not in joined.lower().replace("seen by ai", "")
    assert "mentioned" not in joined
    assert "seen by AI" in joined


def test_audit_page_off_domain_raises_and_persists_nothing(db):
    import pytest
    from app.models.page_audit import PageAudit
    from app.services import citability_service
    from app.services.citability_service import OffDomainUrlError
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True):
        with pytest.raises(OffDomainUrlError):
            citability_service.audit_page(client, "https://rival.com/page", db)
    assert db.query(PageAudit).count() == 0


def test_no_problem_checks_skips_claude(db):
    from app.services import citability_service
    client = _make_client(db)
    ac = _mock_anthropic(_SUGGESTIONS_JSON)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=EXEMPLARY_HTML), \
         patch.object(citability_service, "anthropic_client", return_value=ac):
        audit = citability_service.audit_page(client, "https://acme.com/", db)
    if audit.score == 100:
        ac.messages.create.assert_not_called()
        assert audit.suggestions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_citability_service.py -q`
Expected: new tests FAIL (`AttributeError: ... has no attribute 'audit_page'`); Task 2 tests still pass.

- [ ] **Step 3: Implement**

`backend/app/prompts/citability.py`:

```python
# backend/app/prompts/citability.py
"""Prompt for the page-citability rewrite suggestions (assist-only —
the score is computed server-side; Claude only proposes text)."""
from app.models.client import Client

SUGGESTIONS_VERSION = "v1"


def build_citability_suggestions(client: Client, problem_checks: list[dict], excerpt: str) -> str:
    issues = "\n".join(
        f"- {c['label']} ({c['status']}): {c['detail']}" for c in problem_checks
    )
    return f"""You are a GEO (Generative Engine Optimization) editor helping a {client.industry} \
business called {client.name} make one web page easier for AI assistants to read and quote.

An automated audit of the page found these issues:
{issues}

Page content (first part):
---
{excerpt}
---

Propose up to 5 concrete rewrites that fix the audit issues. For each:
- section: which part of the page it applies to (short label, e.g. "Opening paragraph").
- issue: one plain-English sentence on what's wrong there.
- rewrite: publish-ready replacement text the business can paste in as-is. Write it in \
the page's own voice, factually grounded ONLY in what the page already says — never \
invent services, prices, statistics, or claims.

Never use the words "citation", "cited", "mentioned", "citation rate", "ranking position", \
or "visibility gap" — say "seen by AI" and "visibility frequency" instead.
Output ONLY valid JSON, no code fences, exactly:
{{"suggestions": [{{"section": "string", "issue": "string", "rewrite": "string"}}]}}"""
```

Append to `backend/app/services/citability_service.py` (extend the imports at the top of the file):

```python
import json
import uuid

from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.page_audit import PageAudit
from app.prompts.citability import build_citability_suggestions
from app.services.claude_client import MODEL, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_text
```

and append the functions:

```python
_SUGGESTIONS_MAX_TOKENS = 1024
_EXCERPT_WORDS = 1500
_MAX_SUGGESTIONS = 5


def generate_suggestions(
    client: Client, checks: list[dict], page_text: str, db: Session
) -> tuple[list[dict], bool]:
    """(sanitized suggestion items, failed_flag). Never raises — a Claude
    failure must not lose the audit (spec §7)."""
    problems = [c for c in checks if c["status"] in ("warn", "fail")]
    if not problems:
        return [], False
    excerpt = " ".join(page_text.split()[:_EXCERPT_WORDS])
    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=_SUGGESTIONS_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": build_citability_suggestions(client, problems, excerpt),
            }],
        )
        record_llm_call(
            service="citability_suggestions", model=MODEL, response=response,
            client_id=client.id, db=db,
        )
        payload = json.loads(strip_code_fences(response.content[0].text))
        items = payload.get("suggestions", []) if isinstance(payload, dict) else payload
        cleaned: list[dict] = []
        for item in items[:_MAX_SUGGESTIONS]:
            if not isinstance(item, dict):
                continue
            section = sanitize_text(str(item.get("section", "")).strip())
            issue = sanitize_text(str(item.get("issue", "")).strip())
            rewrite = sanitize_text(str(item.get("rewrite", "")).strip())
            if section and issue and rewrite:
                cleaned.append({"section": section, "issue": issue, "rewrite": rewrite})
        return cleaned, False
    except Exception as exc:
        logger.warning(
            "citability_suggestions_failed", client_id=str(client.id), error=str(exc)
        )
        return [], True


def audit_page(client: Client, url: str, db: Session) -> PageAudit:
    """Validate → fetch → check → score → suggest → persist. One new row per run.

    Raises OffDomainUrlError (route: 422) or PageFetchError (route: 502);
    nothing is persisted on either.
    """
    normalized = validate_audit_url(client.website, url)
    if normalized is None:
        raise OffDomainUrlError(url)
    html = fetch_page(normalized)
    checks = run_citability_checks(html)
    score = compute_citability_score(checks)
    # Suggestions read the same text the checks saw.
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    page_text = soup.get_text(" ", strip=True)
    suggestions, failed = generate_suggestions(client, checks, page_text, db)

    audit = PageAudit(
        client_id=client.id, url=normalized, score=score, checks=checks,
        suggestions=suggestions, suggestions_failed=failed,
    )
    db.add(audit)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="page_audit_run",
        note=f"Page readability audit run on {normalized} — scored {score}/100.",
    ))
    db.commit()
    db.refresh(audit)
    return audit
```

In `backend/app/prompts/registry.py`: add `citability` to the `from app.prompts import (...)` list, and add to `REGISTRY`:

```python
    "citability_suggestions":      {"version": citability.SUGGESTIONS_VERSION,     "model": MODEL},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_citability_service.py tests/test_prompt_registry.py -q 2>&1 | tail -2` (if `test_prompt_registry.py` doesn't exist, run just the citability file)
Expected: all pass (11 in the citability file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/prompts/citability.py backend/app/services/citability_service.py backend/app/prompts/registry.py backend/tests/test_citability_service.py
git commit -m "feat(citability): Claude rewrite suggestions + audit persistence"
```

---

### Task 4: Deliverable service + prompts

**Files:**
- Create: `backend/app/prompts/deliverables.py`
- Create: `backend/app/services/deliverable_service.py`
- Modify: `backend/app/prompts/registry.py`
- Test: `backend/tests/test_deliverable_service.py`

**Interfaces:**
- Produces: `generate_deliverable(client: Client, dtype: str, db: Session, competitor: Competitor | None = None) -> ContentDeliverable | None` (None = Claude failure, nothing persisted — retryable, same contract as content_brief_service); `DELIVERABLE_TYPES = ("faq_pack", "comparison_page", "glossary")`; prompt builders `build_faq_pack(client, lost_queries)`, `build_comparison_page(client, competitor, evidence_lines)`, `build_glossary(client, query_texts)`; versions `FAQ_PACK_VERSION = COMPARISON_PAGE_VERSION = GLOSSARY_VERSION = "v1"`; registry entries `deliverable_faq_pack` / `deliverable_comparison_page` / `deliverable_glossary` on `MODEL_NARRATIVE`.
- Consumes: `MODEL_NARRATIVE` (publish-ready content = high-stakes/low-volume — the assessment precedent), `anthropic_client`, `strip_code_fences`, `record_llm_call`, `sanitize_text`; `Scan`, `ScanQueryResult`, `Competitor`, `ActivityLog` models; `detect_brand_mention` from `brand_detection` (comparison evidence).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_deliverable_service.py`:

```python
"""deliverable_service tests — mocked Anthropic, real db fixture (spec §8)."""
from unittest.mock import MagicMock, patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _make_scan_with_results(db, client, n_lost=3):
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    for i in range(n_lost):
        db.add(ScanQueryResult(
            scan_id=scan.id, platform="chatgpt", category="recommendation",
            query_text=f"best dental clinic in KL {i}",
            response_text="Some answer text naming Rival Dental.",
            brand_detected=False,
        ))
    db.commit()
    return scan


def _mock_anthropic(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    return ac


_ENVELOPE = '{"title": "Dental FAQ Pack", "body_md": "# FAQ\\n\\n**Q:** How much?\\n**A:** RM 120."}'


def test_faq_pack_generates_and_persists_draft(db):
    from app.models.activity_log import ActivityLog
    from app.services import deliverable_service
    client = _make_client(db)
    scan = _make_scan_with_results(db, client)
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "faq_pack", db)
    assert d is not None
    assert d.status == "draft"
    assert d.title == "Dental FAQ Pack"
    assert d.body_md.startswith("# FAQ")
    assert d.source_context["scan_id"] == str(scan.id)
    log = db.query(ActivityLog).filter(ActivityLog.client_id == client.id).one()
    assert log.event_type == "deliverable_generated"


def test_comparison_page_requires_competitor(db):
    import pytest
    from app.services import deliverable_service
    client = _make_client(db)
    with pytest.raises(ValueError):
        deliverable_service.generate_deliverable(client, "comparison_page", db, competitor=None)


def test_comparison_page_generates_with_competitor(db):
    from app.models.competitor import Competitor
    from app.services import deliverable_service
    client = _make_client(db)
    _make_scan_with_results(db, client)
    comp = Competitor(client_id=client.id, name="Rival Dental", website="https://rival.com")
    db.add(comp)
    db.commit()
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "comparison_page", db, competitor=comp)
    assert d is not None
    assert d.competitor_id == comp.id


def test_glossary_generates_without_scan(db):
    from app.services import deliverable_service
    client = _make_client(db)  # no scan at all — profile-only evidence is fine
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d is not None
    assert d.type == "glossary"


def test_claude_failure_persists_nothing(db):
    from app.models.content_deliverable import ContentDeliverable
    from app.services import deliverable_service
    client = _make_client(db)
    with patch.object(deliverable_service, "anthropic_client", side_effect=Exception("down")):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d is None
    assert db.query(ContentDeliverable).count() == 0


def test_banned_language_sanitized_in_body(db):
    from app.services import deliverable_service
    client = _make_client(db)
    dirty = '{"title": "Why Acme is cited", "body_md": "Acme is cited and mentioned often."}'
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(dirty)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert "cited" not in d.body_md
    assert "mentioned" not in d.body_md
    assert "seen by AI" in d.body_md
    assert "cited" not in d.title


def test_regenerate_never_touches_reviewed_row(db):
    from app.core.time import utcnow
    from app.models.content_deliverable import ContentDeliverable
    from app.services import deliverable_service
    client = _make_client(db)
    reviewed = ContentDeliverable(
        client_id=client.id, type="glossary", title="Reviewed glossary",
        body_md="approved text", status="reviewed", reviewed_at=utcnow(),
    )
    db.add(reviewed)
    db.commit()
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d.id != reviewed.id
    db.refresh(reviewed)
    assert reviewed.body_md == "approved text"
    assert reviewed.status == "reviewed"
    assert db.query(ContentDeliverable).count() == 2
```

Note: if `Scan(...)` needs more required fields, copy the minimal construction from an existing test that builds a Scan (e.g. grep `Scan(` in `tests/`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_deliverable_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.deliverable_service'`

- [ ] **Step 3: Implement**

`backend/app/prompts/deliverables.py`:

```python
# backend/app/prompts/deliverables.py
"""Prompts for the three content deliverable generators (Content Studio).

Output is published under the CLIENT's name — every prompt forbids invented
facts, and the comparison prompt additionally enforces a fair tone. The
admin-review gate is mandatory, not decorative.
"""
from app.models.client import Client
from app.models.competitor import Competitor

FAQ_PACK_VERSION = "v1"
COMPARISON_PAGE_VERSION = "v1"
GLOSSARY_VERSION = "v1"

_LANGUAGE_RULES = (
    'Never use the words "citation", "cited", "mentioned", "citation rate", '
    '"ranking position", or "visibility gap" — say "seen by AI" and '
    '"visibility frequency" instead.'
)

_ENVELOPE_RULES = """Output ONLY valid JSON, no code fences, exactly:
{"title": "string", "body_md": "string"}
body_md is complete GitHub-flavoured Markdown, publish-ready."""


def _profile(client: Client) -> str:
    location = ", ".join(p for p in (client.city, client.state, client.country) if p)
    return f"""Business: {client.name} ({client.industry}{f", {location}" if location else ""})
Website: {client.website}
Description: {client.description or "n/a"}
Target audience: {client.target_audience or "n/a"}"""


def build_faq_pack(client: Client, lost_queries: list[str]) -> str:
    queries_block = (
        "\n".join(f"- {q}" for q in lost_queries)
        if lost_queries
        else "- (no scan data yet — infer typical customer questions from the profile)"
    )
    return f"""You are a GEO content writer. Create a publish-ready FAQ pack for this business.

{_profile(client)}

These are real questions people asked AI assistants where {client.name} was not yet seen by AI:
{queries_block}

Write 8-12 Q&A pairs:
- Questions phrased exactly the way a customer would ask an AI assistant.
- Each answer 2-4 sentences, specific to this business, naturally including the business \
name where it reads well. Ground every claim ONLY in the profile above — never invent \
prices, statistics, certifications, or services.
- Cover the lost questions above first, then round out with the most common questions for \
this industry.
- End body_md with a one-line note: "Tip: add this FAQ to your site together with FAQPage \
schema — the SeenBy toolkit generates it."
Format body_md as: H1 title, then "## Question" headings each followed by the answer paragraph.
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""


def build_comparison_page(client: Client, competitor: Competitor, evidence_lines: list[str]) -> str:
    evidence_block = (
        "\n".join(f"- {line}" for line in evidence_lines)
        if evidence_lines
        else "- (no head-to-head data yet)"
    )
    return f"""You are a GEO content writer. Draft a fair, factual comparison page: \
{client.name} vs {competitor.name}.

{_profile(client)}

Competitor: {competitor.name}{f" ({competitor.website})" if competitor.website else ""}

Head-to-head context from AI-assistant answers (admin evidence, do not quote directly):
{evidence_block}

Structure body_md exactly as:
1. H1: "{client.name} vs {competitor.name}: Which Is Right for You?"
2. A 2-3 sentence neutral intro.
3. "## At a glance" — a Markdown comparison table. Rows ONLY for factual aspects you can \
ground in the profile (services, location, audience). Where you don't know the \
competitor's side, write "Check their website" — NEVER invent competitor facts.
4. "## When {client.name} is the better fit" — grounded in the profile only.
5. "## When {competitor.name} may fit" — honest, respectful; no invented weaknesses.
6. "## Frequently asked questions" — 3-4 Q&As about choosing between them.

Hard rules: never disparage {competitor.name}; no invented facts or statistics for either \
business; no superlatives about {client.name} that are not in the profile above.
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""


def build_glossary(client: Client, query_texts: list[str]) -> str:
    queries_block = (
        "\n".join(f"- {q}" for q in query_texts[:40])
        if query_texts
        else "- (no scan data yet — use the industry's standard vocabulary)"
    )
    return f"""You are a GEO content writer. Create an industry glossary page for this business.

{_profile(client)}

Terms and phrasing appear in these real AI-assistant queries about this market:
{queries_block}

Write 15-20 glossary entries:
- Pick the terms a customer of this industry actually encounters (harvest candidates from \
the queries above, then fill with standard industry terms).
- Each entry: "## Term" heading, then ONE plain-English paragraph (2-4 sentences) a \
layperson understands. Definition sentences should start "X is …" — AI assistants quote \
that form directly.
- Where natural (at most 5 entries), relate the term to how {client.name} handles it — \
grounded only in the profile.
- Alphabetical order. H1: "{client.industry} Terms Explained".
{_LANGUAGE_RULES}
{_ENVELOPE_RULES}"""
```

`backend/app/services/deliverable_service.py`:

```python
# backend/app/services/deliverable_service.py
"""Content deliverable generators — FAQ pack, comparison page, glossary.

Claude writes; the admin gates. Drafts persist immediately; only an explicit
PATCH marks a row reviewed, and regeneration always creates a NEW draft
(reviewed rows are retainer deliverables — never overwritten). Claude
failure → None, nothing persisted (same retryable contract as
content_brief_service).
"""
import json
import uuid

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_deliverable import ContentDeliverable
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.prompts.deliverables import build_comparison_page, build_faq_pack, build_glossary
from app.services.brand_detection import detect_brand_mention
from app.services.claude_client import MODEL_NARRATIVE, anthropic_client, strip_code_fences
from app.services.cost_tracker import record_llm_call
from app.services.language_sanitizer import sanitize_text

logger = structlog.get_logger()

DELIVERABLE_TYPES = ("faq_pack", "comparison_page", "glossary")
_MAX_TOKENS = 4096
_MAX_LOST_QUERIES = 10

_TYPE_LABELS = {
    "faq_pack": "FAQ pack",
    "comparison_page": "comparison page",
    "glossary": "industry glossary",
}


def _latest_completed_scan(client_id: uuid.UUID, db: Session) -> Scan | None:
    return (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )


def _client_results(scan: Scan, db: Session) -> list[ScanQueryResult]:
    return (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.hallucination_flagged.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .all()
    )


def _build_evidence(
    client: Client, dtype: str, db: Session, competitor: Competitor | None
) -> tuple[str, dict]:
    """(prompt, source_context). source_context is admin-only provenance."""
    scan = _latest_completed_scan(client.id, db)
    results = _client_results(scan, db) if scan else []

    if dtype == "faq_pack":
        lost = [r for r in results if not r.brand_detected][:_MAX_LOST_QUERIES]
        return build_faq_pack(client, [r.query_text for r in lost]), {
            "scan_id": str(scan.id) if scan else None,
            "result_ids": [str(r.id) for r in lost],
        }

    if dtype == "comparison_page":
        evidence_lines: list[str] = []
        used_ids: list[str] = []
        for r in results:
            if r.response_text and detect_brand_mention(r.response_text, competitor.name):
                outcome = "also seen by AI" if r.brand_detected else "seen by AI while the client was not"
                evidence_lines.append(f'Asked "{r.query_text}": {competitor.name} was {outcome}.')
                used_ids.append(str(r.id))
        return build_comparison_page(client, competitor, evidence_lines), {
            "scan_id": str(scan.id) if scan else None,
            "competitor_id": str(competitor.id),
            "result_ids": used_ids,
        }

    # glossary
    query_texts = sorted({r.query_text for r in results})
    return build_glossary(client, query_texts), {
        "scan_id": str(scan.id) if scan else None,
        "query_count": len(query_texts),
    }


def generate_deliverable(
    client: Client, dtype: str, db: Session, competitor: Competitor | None = None
) -> ContentDeliverable | None:
    """Generate + persist one draft deliverable. None = Claude failure
    (nothing persisted, caller surfaces a retryable error)."""
    if dtype not in DELIVERABLE_TYPES:
        raise ValueError(f"unknown deliverable type: {dtype}")
    if dtype == "comparison_page" and competitor is None:
        raise ValueError("comparison_page requires a competitor")

    prompt, source_context = _build_evidence(client, dtype, db, competitor)

    try:
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        record_llm_call(
            service=f"deliverable_{dtype}", model=MODEL_NARRATIVE, response=response,
            client_id=client.id, db=db,
        )
        payload = json.loads(strip_code_fences(response.content[0].text))
        title = sanitize_text(str(payload["title"]).strip())
        body_md = sanitize_text(str(payload["body_md"]).strip())
        if not title or not body_md:
            raise ValueError("deliverable missing title or body")
    except Exception as exc:
        logger.warning(
            "deliverable_generation_failed",
            client_id=str(client.id), type=dtype, error=str(exc),
        )
        return None

    deliverable = ContentDeliverable(
        client_id=client.id,
        type=dtype,
        competitor_id=competitor.id if competitor else None,
        title=title[:512],
        body_md=body_md,
        source_context=source_context,
    )
    db.add(deliverable)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="deliverable_generated",
        note=f"Content deliverable generated: {_TYPE_LABELS[dtype]} — {title[:80]}",
    ))
    db.commit()
    db.refresh(deliverable)
    return deliverable
```

In `backend/app/prompts/registry.py`: add `deliverables` to the `from app.prompts import (...)` list, and add to `REGISTRY` (publish-ready client content = high-stakes/low-volume → `MODEL_NARRATIVE`, the assessment precedent):

```python
    "deliverable_faq_pack":        {"version": deliverables.FAQ_PACK_VERSION,        "model": MODEL_NARRATIVE},
    "deliverable_comparison_page": {"version": deliverables.COMPARISON_PAGE_VERSION, "model": MODEL_NARRATIVE},
    "deliverable_glossary":        {"version": deliverables.GLOSSARY_VERSION,        "model": MODEL_NARRATIVE},
```

- [ ] **Step 4: Run tests, then the full suite**

Run: `poetry run pytest tests/test_deliverable_service.py -q` → 7 passed.
Run: `poetry run pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/prompts/deliverables.py backend/app/services/deliverable_service.py backend/app/prompts/registry.py backend/tests/test_deliverable_service.py
git commit -m "feat(deliverables): FAQ pack, comparison page, glossary generators"
```

---

### Task 5: API routes + schemas

**Files:**
- Create: `backend/app/schemas/citability.py`
- Create: `backend/app/schemas/deliverable.py`
- Create: `backend/app/api/v1/citability.py`
- Create: `backend/app/api/v1/deliverables.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_api_citability.py`, `backend/tests/test_api_deliverables.py`

**Interfaces:**
- Produces routes: `POST /api/v1/clients/{id}/page-audits` (body `{url}`; 422 off-domain, 502 fetch failure), `GET /api/v1/clients/{id}/page-audits` (latest per URL + `previous_score`), `GET /api/v1/clients/{id}/page-audits/{audit_id}`; `POST /api/v1/clients/{id}/deliverables` (body `{type, competitor_id?}`; 422 bad type / missing competitor; 502 Claude failure), `GET .../deliverables`, `PATCH .../deliverables/{did}` (`{title?, body_md?, status?}`; only draft→reviewed; ActivityLog `deliverable_reviewed` on transition), `GET .../deliverables/{did}/download` (`text/markdown` attachment).
- Consumes: Task 3's `audit_page` + exceptions; Task 4's `generate_deliverable` + `DELIVERABLE_TYPES`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_citability.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme"
    m.website = "https://acme.com"
    m.archived_at = None
    return m


def _fake_audit(client_id, url="https://acme.com/x", score=70):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.client_id = client_id
    a.url = url
    a.score = score
    a.checks = [{"id": "word_count", "label": "Page length", "status": "pass",
                 "detail": "ok", "points": 10}]
    a.suggestions = []
    a.suggestions_failed = False
    a.created_at = datetime(2026, 7, 23)
    return a


def test_run_page_audit_returns_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page",
               return_value=_fake_audit(fake_client.id)) as mock_run:
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://acme.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["score"] == 70
    mock_run.assert_called_once()


def test_run_page_audit_422_off_domain():
    from app.services.citability_service import OffDomainUrlError
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page", side_effect=OffDomainUrlError("x")):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://rival.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_run_page_audit_502_fetch_failure():
    from app.services.citability_service import PageFetchError
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.citability.audit_page", side_effect=PageFetchError("x")):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/page-audits",
            json={"url": "https://acme.com/x"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_list_returns_latest_per_url_with_previous_score(db):
    # Real db fixture: three audits over two URLs.
    from app.models.client import Client
    from app.models.page_audit import PageAudit
    from app.api.v1.citability import get_page_audit_list
    client = Client(name="Acme", website="https://acme.com",
                    industry="Dental", contact_email="a@b.co")
    db.add(client)
    db.commit()
    from datetime import datetime
    old = PageAudit(client_id=client.id, url="https://acme.com/a", score=40,
                    checks=[], created_at=datetime(2026, 7, 1))
    new = PageAudit(client_id=client.id, url="https://acme.com/a", score=75,
                    checks=[], created_at=datetime(2026, 7, 20))
    other = PageAudit(client_id=client.id, url="https://acme.com/b", score=60,
                      checks=[], created_at=datetime(2026, 7, 10))
    db.add_all([old, new, other])
    db.commit()
    items = get_page_audit_list(client.id, db)
    by_url = {i["url"]: i for i in items}
    assert by_url["https://acme.com/a"]["score"] == 75
    assert by_url["https://acme.com/a"]["previous_score"] == 40
    assert by_url["https://acme.com/b"]["previous_score"] is None


@pytest.mark.parametrize("method,path", [
    ("post", "page-audits"),
    ("get", "page-audits"),
    ("get", f"page-audits/{uuid.uuid4()}"),
])
def test_page_audit_routes_require_auth(method, path):
    from app.main import app
    resp = getattr(TestClient(app), method)(f"/api/v1/clients/{uuid.uuid4()}/{path}")
    assert resp.status_code == 401
```

`backend/tests/test_api_deliverables.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme"
    m.website = "https://acme.com"
    m.archived_at = None
    return m


def _fake_deliverable(client_id, status="draft"):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.client_id = client_id
    d.type = "faq_pack"
    d.competitor_id = None
    d.title = "FAQ pack"
    d.body_md = "# FAQ"
    d.status = status
    d.generated_at = datetime(2026, 7, 23)
    d.reviewed_at = None
    return d


def test_generate_deliverable_returns_draft():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.deliverables.generate_deliverable",
               return_value=_fake_deliverable(fake_client.id)):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "faq_pack"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


def test_generate_unknown_type_422():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "poem"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_comparison_requires_competitor_id():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "comparison_page"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_generate_claude_failure_502():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.deliverables.generate_deliverable", return_value=None):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/deliverables", json={"type": "glossary"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_patch_marks_reviewed_and_logs():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id, status="draft")
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).patch(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}",
        json={"status": "reviewed"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert d.status == "reviewed"
    assert d.reviewed_at is not None
    assert mock_db.add.called  # ActivityLog deliverable_reviewed
    assert mock_db.commit.called


def test_patch_reviewed_back_to_draft_rejected():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id, status="reviewed")
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).patch(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}",
        json={"status": "draft"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_download_returns_markdown_attachment():
    app, get_db = _make_app()
    fake_client = _fake_client()
    d = _fake_deliverable(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, d]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).get(
        f"/api/v1/clients/{fake_client.id}/deliverables/{d.id}/download"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.text == "# FAQ"


@pytest.mark.parametrize("method,path", [
    ("post", "deliverables"),
    ("get", "deliverables"),
    ("patch", f"deliverables/{uuid.uuid4()}"),
    ("get", f"deliverables/{uuid.uuid4()}/download"),
])
def test_deliverable_routes_require_auth(method, path):
    from app.main import app
    resp = getattr(TestClient(app), method)(f"/api/v1/clients/{uuid.uuid4()}/{path}")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_api_citability.py tests/test_api_deliverables.py -q`
Expected: FAIL — 404s / ImportErrors.

- [ ] **Step 3: Implement**

`backend/app/schemas/citability.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class PageAuditRequest(BaseModel):
    url: str


class PageAuditCheck(BaseModel):
    id: str
    label: str
    status: str  # "pass" | "warn" | "fail"
    detail: str
    points: int  # earned


class PageAuditSuggestion(BaseModel):
    section: str
    issue: str
    rewrite: str


class PageAuditResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    url: str
    score: int
    checks: list[PageAuditCheck]
    suggestions: list[PageAuditSuggestion]
    suggestions_failed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PageAuditListItem(BaseModel):
    id: uuid.UUID
    url: str
    score: int
    previous_score: int | None
    created_at: datetime
```

`backend/app/schemas/deliverable.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class DeliverableCreate(BaseModel):
    type: str
    competitor_id: uuid.UUID | None = None


class DeliverableUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    status: str | None = None  # only "reviewed" accepted


class DeliverableResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    type: str
    competitor_id: uuid.UUID | None
    title: str
    body_md: str
    status: str
    generated_at: datetime
    reviewed_at: datetime | None
    # source_context is deliberately NOT exposed — admin-only provenance kept
    # server-side; the UI doesn't need it.

    model_config = {"from_attributes": True}
```

`backend/app/api/v1/citability.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.page_audit import PageAudit
from app.schemas.citability import PageAuditListItem, PageAuditRequest, PageAuditResponse
from app.services.citability_service import OffDomainUrlError, PageFetchError, audit_page

router = APIRouter(prefix="/clients/{client_id}/page-audits", tags=["citability"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.post("", response_model=PageAuditResponse, dependencies=[Depends(require_api_key)])
def run_audit(client_id: uuid.UUID, body: PageAuditRequest, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    try:
        return audit_page(client, body.url, db)
    except OffDomainUrlError:
        raise HTTPException(
            status_code=422,
            detail="That page isn't on this client's website — audits only run on the client's own domain.",
        )
    except PageFetchError:
        raise HTTPException(
            status_code=502,
            detail="Couldn't load that page — check the address and try again.",
        )


def get_page_audit_list(client_id: uuid.UUID, db: Session) -> list[dict]:
    """Latest audit per distinct URL, with the previous score for a delta arrow."""
    rows = (
        db.query(PageAudit)
        .filter(PageAudit.client_id == client_id)
        .order_by(PageAudit.created_at.desc())
        .all()
    )
    latest: dict[str, PageAudit] = {}
    previous: dict[str, int] = {}
    for r in rows:
        if r.url not in latest:
            latest[r.url] = r
        elif r.url not in previous:
            previous[r.url] = r.score
    return [
        {
            "id": a.id, "url": a.url, "score": a.score,
            "previous_score": previous.get(url), "created_at": a.created_at,
        }
        for url, a in latest.items()
    ]


@router.get("", response_model=list[PageAuditListItem], dependencies=[Depends(require_api_key)])
def list_audits(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return get_page_audit_list(client_id, db)


@router.get("/{audit_id}", response_model=PageAuditResponse, dependencies=[Depends(require_api_key)])
def get_audit(client_id: uuid.UUID, audit_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    audit = db.get(PageAudit, audit_id)
    if not audit or audit.client_id != client_id:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit
```

`backend/app/api/v1/deliverables.py`:

```python
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_deliverable import ContentDeliverable
from app.schemas.deliverable import DeliverableCreate, DeliverableResponse, DeliverableUpdate
from app.services.deliverable_service import DELIVERABLE_TYPES, generate_deliverable

router = APIRouter(prefix="/clients/{client_id}/deliverables", tags=["deliverables"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _get_deliverable_or_404(
    client_id: uuid.UUID, deliverable_id: uuid.UUID, db: Session
) -> ContentDeliverable:
    d = db.get(ContentDeliverable, deliverable_id)
    if not d or d.client_id != client_id:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return d


@router.post("", response_model=DeliverableResponse, dependencies=[Depends(require_api_key)])
def create(client_id: uuid.UUID, body: DeliverableCreate, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    if body.type not in DELIVERABLE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown deliverable type: {body.type}")
    competitor = None
    if body.type == "comparison_page":
        if body.competitor_id is None:
            raise HTTPException(status_code=422, detail="A comparison page needs a competitor")
        competitor = db.get(Competitor, body.competitor_id)
        if not competitor or competitor.client_id != client_id:
            raise HTTPException(status_code=404, detail="Competitor not found")
    deliverable = generate_deliverable(client, body.type, db, competitor=competitor)
    if deliverable is None:
        raise HTTPException(
            status_code=502, detail="Generation didn't complete — try again."
        )
    return deliverable


@router.get("", response_model=list[DeliverableResponse], dependencies=[Depends(require_api_key)])
def list_deliverables(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return (
        db.query(ContentDeliverable)
        .filter(ContentDeliverable.client_id == client_id)
        .order_by(ContentDeliverable.generated_at.desc())
        .all()
    )


@router.patch(
    "/{deliverable_id}", response_model=DeliverableResponse,
    dependencies=[Depends(require_api_key)],
)
def update(
    client_id: uuid.UUID, deliverable_id: uuid.UUID,
    body: DeliverableUpdate, db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    d = _get_deliverable_or_404(client_id, deliverable_id, db)
    if body.status is not None and body.status != "reviewed":
        raise HTTPException(status_code=422, detail="Status can only move to reviewed")
    if body.title is not None:
        d.title = body.title[:512]
    if body.body_md is not None:
        d.body_md = body.body_md
    if body.status == "reviewed" and d.status != "reviewed":
        d.status = "reviewed"
        d.reviewed_at = datetime.now(UTC)
        db.add(ActivityLog(
            client_id=client_id,
            event_type="deliverable_reviewed",
            note=f"Content deliverable reviewed: {d.title[:80]}",
        ))
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}/download", dependencies=[Depends(require_api_key)])
def download(client_id: uuid.UUID, deliverable_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    d = _get_deliverable_or_404(client_id, deliverable_id, db)
    filename = f"{d.type}-{d.generated_at:%Y%m%d}.md"
    return Response(
        content=d.body_md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

`backend/app/api/v1/router.py` — add `citability, deliverables` to the import and:

```python
router.include_router(citability.router)
router.include_router(deliverables.router)
```

- [ ] **Step 4: Run the touched tests, then the full suite**

Run: `poetry run pytest tests/test_api_citability.py tests/test_api_deliverables.py -q` → all pass.
Run: `poetry run pytest -q` → all pass. Then `poetry run ruff check app workers tests` → "All checks passed!".

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/citability.py backend/app/schemas/deliverable.py backend/app/api/v1/citability.py backend/app/api/v1/deliverables.py backend/app/api/v1/router.py backend/tests/test_api_citability.py backend/tests/test_api_deliverables.py
git commit -m "feat(citability): page-audit + deliverable API routes"
```

---

### Task 6: Content Studio — page audits UI + nav

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/app/clients/[id]/content-studio/actions.ts`
- Create: `frontend/src/app/clients/[id]/content-studio/PageAuditsSection.tsx`
- Create: `frontend/src/app/clients/[id]/content-studio/page.tsx` (Deliverables section arrives in Task 7 — the page renders audits only for now)
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `CLAUDE.md` (§9 nav)

**Interfaces:**
- Produces: types `PageAuditCheck, PageAuditSuggestion, PageAudit, PageAuditListItem, DeliverableType, ContentDeliverable`; api fns `runPageAudit, getPageAudits, getPageAudit, generateDeliverable, getDeliverables, updateDeliverable` (deliverable fns consumed by Task 7); actions `runPageAuditAction, getPageAuditDetailAction`.
- Consumes: Task 5's endpoints; `getScoreColor` from `src/lib/score-utils.ts`.

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```ts
// ── Content Studio ───────────────────────────────────────────────────────────

export interface PageAuditCheck {
  id: string
  label: string
  status: "pass" | "warn" | "fail"
  detail: string
  points: number
}

export interface PageAuditSuggestion {
  section: string
  issue: string
  rewrite: string
}

export interface PageAudit {
  id: string
  client_id: string
  url: string
  score: number
  checks: PageAuditCheck[]
  suggestions: PageAuditSuggestion[]
  suggestions_failed: boolean
  created_at: string
}

export interface PageAuditListItem {
  id: string
  url: string
  score: number
  previous_score: number | null
  created_at: string
}

export type DeliverableType = "faq_pack" | "comparison_page" | "glossary"

export interface ContentDeliverable {
  id: string
  client_id: string
  type: DeliverableType
  competitor_id: string | null
  title: string
  body_md: string
  status: "draft" | "reviewed"
  generated_at: string
  reviewed_at: string | null
}
```

- [ ] **Step 2: Add api.ts functions**

Append to `frontend/src/lib/api.ts` (add `PageAudit, PageAuditListItem, ContentDeliverable, DeliverableType` to the type imports):

```ts
// ── Content Studio ───────────────────────────────────────────────────────────

export function runPageAudit(clientId: string, url: string): Promise<PageAudit> {
  return apiFetch<PageAudit>(`/api/v1/clients/${clientId}/page-audits`, {
    method: "POST",
    body: JSON.stringify({ url }),
  })
}

export function getPageAudits(clientId: string): Promise<PageAuditListItem[]> {
  return apiFetch<PageAuditListItem[]>(`/api/v1/clients/${clientId}/page-audits`)
}

export function getPageAudit(clientId: string, auditId: string): Promise<PageAudit> {
  return apiFetch<PageAudit>(`/api/v1/clients/${clientId}/page-audits/${auditId}`)
}

export function generateDeliverable(
  clientId: string,
  type: DeliverableType,
  competitorId?: string,
): Promise<ContentDeliverable> {
  return apiFetch<ContentDeliverable>(`/api/v1/clients/${clientId}/deliverables`, {
    method: "POST",
    body: JSON.stringify({ type, competitor_id: competitorId ?? null }),
  })
}

export function getDeliverables(clientId: string): Promise<ContentDeliverable[]> {
  return apiFetch<ContentDeliverable[]>(`/api/v1/clients/${clientId}/deliverables`)
}

export function updateDeliverable(
  clientId: string,
  deliverableId: string,
  patch: { title?: string; body_md?: string; status?: "reviewed" },
): Promise<ContentDeliverable> {
  return apiFetch<ContentDeliverable>(
    `/api/v1/clients/${clientId}/deliverables/${deliverableId}`,
    { method: "PATCH", body: JSON.stringify(patch) },
  )
}
```

Check how existing POST helpers in this file pass bodies — if `apiFetch` sets JSON headers itself or expects a plain object, match that convention instead of `JSON.stringify` (read the `apiFetch` implementation at the top of the file and copy an existing body-carrying call like `syncTraffic`/`updateClient`).

- [ ] **Step 3: Add server actions**

`frontend/src/app/clients/[id]/content-studio/actions.ts`:

```ts
"use server"

import { revalidatePath } from "next/cache"
import {
  runPageAudit,
  getPageAudit,
  generateDeliverable,
  updateDeliverable,
} from "@/lib/api"
import type { ContentDeliverable, DeliverableType, PageAudit } from "@/types"

export async function runPageAuditAction(clientId: string, url: string): Promise<PageAudit> {
  const audit = await runPageAudit(clientId, url)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return audit
}

export async function getPageAuditDetailAction(
  clientId: string,
  auditId: string,
): Promise<PageAudit> {
  return getPageAudit(clientId, auditId)
}

export async function generateDeliverableAction(
  clientId: string,
  type: DeliverableType,
  competitorId?: string,
): Promise<ContentDeliverable> {
  const d = await generateDeliverable(clientId, type, competitorId)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return d
}

export async function updateDeliverableAction(
  clientId: string,
  deliverableId: string,
  patch: { title?: string; body_md?: string; status?: "reviewed" },
): Promise<ContentDeliverable> {
  const d = await updateDeliverable(clientId, deliverableId, patch)
  revalidatePath(`/clients/${clientId}/content-studio`)
  return d
}
```

- [ ] **Step 4: Create the Page Audits section component**

`frontend/src/app/clients/[id]/content-studio/PageAuditsSection.tsx`:

```tsx
"use client"

import { useState, useTransition } from "react"
import {
  Loader2, Copy, ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight,
  CheckCircle, AlertTriangle, XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/utils"
import { getScoreColor } from "@/lib/score-utils"
import { runPageAuditAction, getPageAuditDetailAction } from "./actions"
import type { PageAudit, PageAuditListItem } from "@/types"

const SCORE_CLASSES: Record<string, string> = {
  green: "border-score-strong/30 bg-score-strong-bg text-score-strong",
  yellow: "border-score-watch/30 bg-score-watch-bg text-score-watch",
  red: "border-destructive/30 bg-destructive/10 text-destructive",
}

function ScoreChip({ score }: { score: number }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-0.5 text-sm font-semibold tabular-nums ${
        SCORE_CLASSES[getScoreColor(score)]
      }`}
    >
      {score}
    </span>
  )
}

function StatusIcon({ status }: { status: "pass" | "warn" | "fail" }) {
  if (status === "pass") return <CheckCircle className="h-3.5 w-3.5 text-score-strong shrink-0" />
  if (status === "warn") return <AlertTriangle className="h-3.5 w-3.5 text-score-watch shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
}

export function PageAuditsSection({
  clientId,
  initialAudits,
}: {
  clientId: string
  initialAudits: PageAuditListItem[]
}) {
  const [audits, setAudits] = useState<PageAuditListItem[]>(initialAudits)
  const [url, setUrl] = useState("")
  const [runError, setRunError] = useState<string | null>(null)
  const [running, startRun] = useTransition()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PageAudit | null>(null)
  const [loadingDetail, startDetail] = useTransition()

  function handleRun() {
    if (!url.trim()) return
    setRunError(null)
    startRun(async () => {
      try {
        const audit = await runPageAuditAction(clientId, url.trim())
        setAudits((prev) => {
          const rest = prev.filter((a) => a.url !== audit.url)
          const previous = prev.find((a) => a.url === audit.url)
          return [
            {
              id: audit.id, url: audit.url, score: audit.score,
              previous_score: previous ? previous.score : null,
              created_at: audit.created_at,
            },
            ...rest,
          ]
        })
        setDetail(audit)
        setExpandedId(audit.id)
        setUrl("")
      } catch (e) {
        setRunError(
          e instanceof Error && e.message.includes("422")
            ? "That page isn't on this client's website."
            : "Couldn't audit that page — check the address and try again.",
        )
      }
    })
  }

  function handleExpand(item: PageAuditListItem) {
    if (expandedId === item.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(item.id)
    setDetail(null)
    startDetail(async () => {
      try {
        setDetail(await getPageAuditDetailAction(clientId, item.id))
      } catch {
        setDetail(null)
      }
    })
  }

  async function handleCopy(text: string) {
    const ok = await copyToClipboard(text)
    toast[ok ? "success" : "error"](ok ? "Copied to clipboard" : "Couldn't copy.")
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <h3 className="font-display text-lg font-semibold">Page Audits</h3>
      <p className="text-sm text-muted-foreground mt-1">
        Score any page on the client&apos;s site for how easily AI assistants can read
        and quote it. Informational only — not part of the GEO score.
      </p>

      <div className="mt-4 flex gap-2">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleRun()}
          placeholder="https://clientdomain.com/services"
          className="max-w-xl"
        />
        <Button onClick={handleRun} disabled={running || !url.trim()}>
          {running && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {running ? "Auditing…" : "Run audit"}
        </Button>
      </div>
      {runError && <p className="mt-2 text-sm text-destructive">{runError}</p>}

      {audits.length === 0 && !running && (
        <p className="mt-4 text-sm text-muted-foreground">
          No pages audited yet — paste a page address above to start.
        </p>
      )}

      {audits.length > 0 && (
        <div className="mt-4 divide-y rounded-md border">
          {audits.map((item) => (
            <div key={item.id}>
              <button
                onClick={() => handleExpand(item)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/30"
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{item.url}</span>
                <span className="flex shrink-0 items-center gap-3">
                  {item.previous_score !== null && item.previous_score !== item.score && (
                    <span
                      className={`flex items-center gap-0.5 text-xs tabular-nums ${
                        item.score > item.previous_score ? "text-score-strong" : "text-destructive"
                      }`}
                    >
                      {item.score > item.previous_score ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      was {item.previous_score}
                    </span>
                  )}
                  <ScoreChip score={item.score} />
                  <span className="text-xs text-muted-foreground">
                    {new Date(item.created_at).toLocaleDateString("en-MY", {
                      day: "numeric", month: "short",
                    })}
                  </span>
                  {expandedId === item.id ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                </span>
              </button>

              {expandedId === item.id && (
                <div className="border-t bg-muted/10 px-4 py-4">
                  {loadingDetail && !detail && (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                  {detail && detail.id === item.id && (
                    <div className="space-y-4">
                      <div className="divide-y rounded-md border bg-card">
                        {detail.checks.map((check) => (
                          <div key={check.id} className="flex items-start gap-2.5 px-3 py-2">
                            <StatusIcon status={check.status} />
                            <div className="min-w-0">
                              <p className="text-sm font-medium">
                                {check.label}{" "}
                                <span className="text-xs font-normal text-muted-foreground tabular-nums">
                                  {check.points} pts
                                </span>
                              </p>
                              <p className="text-xs text-muted-foreground">{check.detail}</p>
                            </div>
                          </div>
                        ))}
                      </div>

                      {detail.suggestions.length > 0 && (
                        <div>
                          <p className="mb-2 text-sm font-semibold">Suggested rewrites</p>
                          <div className="space-y-2">
                            {detail.suggestions.map((s, i) => (
                              <div key={i} className="rounded-md border bg-card px-3 py-2.5">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="min-w-0">
                                    <p className="text-sm font-medium">{s.section}</p>
                                    <p className="text-xs text-muted-foreground">{s.issue}</p>
                                  </div>
                                  <Button
                                    size="sm" variant="outline" className="h-7 shrink-0 text-xs"
                                    onClick={() => handleCopy(s.rewrite)}
                                  >
                                    <Copy className="h-3 w-3 mr-1" /> Copy
                                  </Button>
                                </div>
                                <p className="mt-2 whitespace-pre-wrap rounded bg-muted/30 px-2.5 py-2 text-sm">
                                  {s.rewrite}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {detail.suggestions_failed && (
                        <p className="text-sm text-muted-foreground">
                          Rewrite suggestions didn&apos;t generate this time —{" "}
                          <button
                            className="underline underline-offset-4"
                            onClick={() => {
                              setUrl(detail.url)
                              handleRun()
                            }}
                          >
                            retry the audit
                          </button>
                          .
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

Note: if `@/components/ui/input` does not exist, check `ls frontend/src/components/ui/` — if missing, use the same `<input>` styling as an existing page with a text input (e.g. settings) rather than adding a new shadcn component ad hoc.

- [ ] **Step 5: Create the page (audits only for now)**

`frontend/src/app/clients/[id]/content-studio/page.tsx`:

```tsx
import { getPageAudits } from "@/lib/api"
import { PageAuditsSection } from "./PageAuditsSection"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentStudioPage({ params }: Props) {
  const { id } = await params
  const audits = await getPageAudits(id).catch(() => [])
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Content Studio</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Page-level AI readability audits and publish-ready content drafts.
        </p>
      </div>
      <PageAuditsSection clientId={id} initialAudits={audits} />
    </div>
  )
}
```

- [ ] **Step 6: Nav — Sidebar + CLAUDE.md §9**

In `frontend/src/components/layout/Sidebar.tsx`: add `PenTool` to the lucide-react import list, and in `CLIENT_NAV` insert after the content-roadmap line:

```tsx
  { href: "/content-studio", label: "Content Studio",      icon: PenTool },
```

In `CLAUDE.md` §9, insert after the content-roadmap line:

```
/clients/[id]/content-studio→ content studio (page citability audits + content deliverables)
```

- [ ] **Step 7: Typecheck + build**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run build
```
Expected: both clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts "frontend/src/app/clients/[id]/content-studio/" frontend/src/components/layout/Sidebar.tsx CLAUDE.md
git commit -m "feat(content-studio): page audits UI + nav entry"
```

---

### Task 7: Content Studio — deliverables UI + cross-links

**Files:**
- Create: `frontend/src/app/clients/[id]/content-studio/DeliverablesSection.tsx`
- Modify: `frontend/src/app/clients/[id]/content-studio/page.tsx`
- Modify: `frontend/src/app/clients/[id]/content-gaps/ContentGapsClient.tsx` (header link)
- Modify: `frontend/src/app/clients/[id]/content-roadmap/ContentRoadmapClient.tsx` (header link)

**Interfaces:**
- Consumes: Task 6's `generateDeliverableAction`, `updateDeliverableAction`, `getDeliverables` api fn, `ContentDeliverable`/`DeliverableType` types; competitors list via `getCompetitorIntelligence` (existing api fn — `data.competitors` has `{id, name}`).

- [ ] **Step 1: Create the Deliverables section**

`frontend/src/app/clients/[id]/content-studio/DeliverablesSection.tsx`:

```tsx
"use client"

import { useState, useTransition } from "react"
import { Loader2, Download, Pencil, Check, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { toast } from "sonner"
import { generateDeliverableAction, updateDeliverableAction } from "./actions"
import type { ContentDeliverable, DeliverableType } from "@/types"

const TYPE_LABELS: Record<DeliverableType, string> = {
  faq_pack: "FAQ pack",
  comparison_page: "Comparison page",
  glossary: "Industry glossary",
}

export function DeliverablesSection({
  clientId,
  initialDeliverables,
  competitors,
}: {
  clientId: string
  initialDeliverables: ContentDeliverable[]
  competitors: { id: string; name: string }[]
}) {
  const [items, setItems] = useState<ContentDeliverable[]>(initialDeliverables)
  const [competitorId, setCompetitorId] = useState<string>("")
  const [generating, setGenerating] = useState<DeliverableType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editBody, setEditBody] = useState("")
  const [, startTransition] = useTransition()

  function handleGenerate(type: DeliverableType) {
    if (type === "comparison_page" && !competitorId) {
      setError("Pick a competitor for the comparison page first.")
      return
    }
    setError(null)
    setGenerating(type)
    startTransition(async () => {
      try {
        const d = await generateDeliverableAction(
          clientId, type, type === "comparison_page" ? competitorId : undefined,
        )
        setItems((prev) => [d, ...prev])
        setOpenId(d.id)
      } catch {
        setError("Generation didn't complete — try again.")
      } finally {
        setGenerating(null)
      }
    })
  }

  function handleMarkReviewed(d: ContentDeliverable) {
    startTransition(async () => {
      try {
        const updated = await updateDeliverableAction(clientId, d.id, { status: "reviewed" })
        setItems((prev) => prev.map((x) => (x.id === d.id ? updated : x)))
        toast.success("Marked as reviewed")
      } catch {
        toast.error("Couldn't update — try again.")
      }
    })
  }

  function handleSaveEdit(d: ContentDeliverable) {
    startTransition(async () => {
      try {
        const updated = await updateDeliverableAction(clientId, d.id, { body_md: editBody })
        setItems((prev) => prev.map((x) => (x.id === d.id ? updated : x)))
        setEditingId(null)
        toast.success("Saved")
      } catch {
        toast.error("Couldn't save — try again.")
      }
    })
  }

  function handleDownload(d: ContentDeliverable) {
    const blob = new Blob([d.body_md], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${d.type}-${d.generated_at.slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <h3 className="font-display text-lg font-semibold">Content Deliverables</h3>
      <p className="text-sm text-muted-foreground mt-1">
        Publish-ready drafts built from scan evidence. Every draft needs your review
        before it counts as delivered.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          onClick={() => handleGenerate("faq_pack")}
          disabled={generating !== null}
        >
          {generating === "faq_pack" && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Generate FAQ pack
        </Button>
        <Button
          variant="outline"
          onClick={() => handleGenerate("glossary")}
          disabled={generating !== null}
        >
          {generating === "glossary" && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Generate glossary
        </Button>
        <div className="flex items-center gap-2">
          <Select value={competitorId} onValueChange={setCompetitorId}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Pick competitor…" />
            </SelectTrigger>
            <SelectContent>
              {competitors.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={() => handleGenerate("comparison_page")}
            disabled={generating !== null || competitors.length === 0}
          >
            {generating === "comparison_page" && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            Generate comparison page
          </Button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

      {items.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing generated yet — the FAQ pack is the quickest win.
        </p>
      )}

      {items.length > 0 && (
        <div className="mt-4 space-y-3">
          {items.map((d) => (
            <div key={d.id} className="overflow-hidden rounded-md border">
              <button
                onClick={() => setOpenId(openId === d.id ? null : d.id)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-muted/30"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{d.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {TYPE_LABELS[d.type]} ·{" "}
                    {new Date(d.generated_at).toLocaleDateString("en-MY", {
                      day: "numeric", month: "short", year: "numeric",
                    })}
                  </span>
                </span>
                {d.status === "reviewed" ? (
                  <Badge className="shrink-0 gap-1 border-score-strong/30 bg-score-strong-bg text-score-strong">
                    <Check className="h-3 w-3" /> Reviewed
                  </Badge>
                ) : (
                  <Badge variant="outline" className="shrink-0 text-muted-foreground">Draft</Badge>
                )}
              </button>

              {openId === d.id && (
                <div className="border-t bg-muted/10 px-4 py-4 space-y-3">
                  {editingId === d.id ? (
                    <>
                      <textarea
                        value={editBody}
                        onChange={(e) => setEditBody(e.target.value)}
                        rows={16}
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono focus:outline-none"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => handleSaveEdit(d)}>
                          <Check className="h-3.5 w-3.5 mr-1" /> Save
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                          <X className="h-3.5 w-3.5 mr-1" /> Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <>
                      <article className="whitespace-pre-wrap rounded-md border bg-card px-4 py-3 text-sm leading-relaxed">
                        {d.body_md}
                      </article>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm" variant="outline"
                          onClick={() => {
                            setEditingId(d.id)
                            setEditBody(d.body_md)
                          }}
                        >
                          <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                        </Button>
                        {d.status === "draft" && (
                          <Button size="sm" onClick={() => handleMarkReviewed(d)}>
                            <Check className="h-3.5 w-3.5 mr-1" /> Mark reviewed
                          </Button>
                        )}
                        <Button size="sm" variant="outline" onClick={() => handleDownload(d)}>
                          <Download className="h-3.5 w-3.5 mr-1" /> Download .md
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

(Markdown preview renders as `whitespace-pre-wrap` text — the repo's established pattern for generated long-form content, see `ContentRoadmapClient.tsx:143`; no markdown library exists in this project and we're not adding one for v1.)

- [ ] **Step 2: Wire it into the page**

Replace `frontend/src/app/clients/[id]/content-studio/page.tsx` with:

```tsx
import { getPageAudits, getDeliverables, getCompetitorIntelligence } from "@/lib/api"
import { PageAuditsSection } from "./PageAuditsSection"
import { DeliverablesSection } from "./DeliverablesSection"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ContentStudioPage({ params }: Props) {
  const { id } = await params
  const [audits, deliverables, intel] = await Promise.all([
    getPageAudits(id).catch(() => []),
    getDeliverables(id).catch(() => []),
    getCompetitorIntelligence(id).catch(() => null),
  ])
  const competitors = (intel?.competitors ?? []).map((c) => ({ id: c.id, name: c.name ?? "Unnamed" }))
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Content Studio</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Page-level AI readability audits and publish-ready content drafts.
        </p>
      </div>
      <PageAuditsSection clientId={id} initialAudits={audits} />
      <DeliverablesSection
        clientId={id}
        initialDeliverables={deliverables}
        competitors={competitors}
      />
    </div>
  )
}
```

- [ ] **Step 3: Cross-links from content pages**

In `frontend/src/app/clients/[id]/content-gaps/ContentGapsClient.tsx` and `frontend/src/app/clients/[id]/content-roadmap/ContentRoadmapClient.tsx`: find each component's header block (the `<h2>`/description at the top) and add directly under the description paragraph:

```tsx
<Link
  href={`/clients/${clientId}/content-studio`}
  className="mt-1 inline-block text-sm text-primary underline-offset-4 hover:underline"
>
  Turn these into content &rarr;
</Link>
```

Add `import Link from "next/link"` if not present. Both components already receive `clientId` as a prop — verify the exact prop name in each file and use it. No other logic changes on those pages.

- [ ] **Step 4: Typecheck + build**

Run from `frontend/`:

```bash
npx tsc --noEmit
npm run build
```
Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/clients/[id]/content-studio/" "frontend/src/app/clients/[id]/content-gaps/ContentGapsClient.tsx" "frontend/src/app/clients/[id]/content-roadmap/ContentRoadmapClient.tsx"
git commit -m "feat(content-studio): deliverables UI + cross-links from content pages"
```

---

### Task 8: Verification gate + walkthrough

**Files:** none (verification only)

- [ ] **Step 1: Run the seenby-verify skill** — full backend pytest + ruff, frontend typecheck + build, banned-language grep, single alembic head. Fix anything it flags.

- [ ] **Step 2: Banned-language spot check on the new client-facing strings**

```bash
grep -rniE "\b(cited|uncited|mentioned|citation rate|ranking position|visibility gap)\b" backend/app/services/citability_service.py backend/app/services/deliverable_service.py backend/app/prompts/citability.py backend/app/prompts/deliverables.py "frontend/src/app/clients/[id]/content-studio/"
```
Expected: matches ONLY inside the prompts' negative instructions ('Never use the words "…"') — none in check details, UI strings, or activity notes.

- [ ] **Step 3: Live walkthrough** (dev servers via the `run-app` skill; prod migration must be applied first via seenby-release, or DB-write actions will 500 against the prod-pointed local backend):
  1. Sidebar shows "Content Studio"; page renders both sections.
  2. Run a page audit on a real client page → score chip with band color, checks grouped with pass/warn/fail icons, suggestions with working Copy buttons; ActivityLog shows `page_audit_run`.
  3. Re-audit the same URL → delta arrow ("was N") appears.
  4. Generate an FAQ pack (real Claude call) → draft appears; edit body, Save; Mark reviewed → badge flips, `deliverable_reviewed` in activity; Download produces a .md file.
  5. Generate a comparison page with a competitor picked; read the draft for tone (no disparagement, no invented facts) — this is the admin gate working as designed.
  6. Confirm `/view/[token]` shows nothing new.

- [ ] **Step 4: Report** — state what passed with output, what was walked through visually, and that the **prod Supabase migration has NOT been run** unless it explicitly was (seenby-release at deploy).

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** §3.1 checks/points/score/Claude-pass → Tasks 2-3; §3.2 model+history → Task 1; §3.3 three routes → Task 5; §4.1 three generators + fair-tone rules → Task 4; §4.2 model + draft/reviewed lifecycle → Tasks 1, 4, 5; §4.3 four routes incl. download → Task 5; §5 Content Studio + nav + §9 update + cross-links, client view untouched → Tasks 6-7; §6 cost control service names + registry → Tasks 3-4; §7 error handling (422/502/empty-suggestions/None-deliverable) → Tasks 3-5; §8 all six listed test behaviors → Tasks 2-5; §9 build order preserved.
- **Deliberate judgment calls** (spec silent or conflicting): (1) `suggestions_failed` bool column added beyond the spec's model sketch — the spec's §3.1 "retry flag" needs persistence to survive a page reload; (2) deliverables use `MODEL_NARRATIVE`, suggestions use `MODEL` — the assessment precedent (high-stakes/low-volume vs assist-volume); (3) Markdown preview is `whitespace-pre-wrap` plain text, not rendered HTML — repo precedent (ContentRoadmapClient), no markdown lib in the project, spec's "rendered" deferred rather than adding a dependency; (4) frontend Download uses a client-side blob of `body_md` (the server-side `/download` route exists per spec but a browser link can't carry the bearer header); (5) `competitor_id` FK is SET NULL so deleting a competitor keeps the deliverable draft; (6) per-check warn thresholds (e.g. lead ≤100 words, question ratio ≥10%, median ≤120) are defined here since the spec only fixed the pass thresholds.
- **Type consistency:** check dict `{id,label,status,detail,points}` identical across service, schema, tests, TS; `generate_deliverable(client, dtype, db, competitor=None)` signature matches route usage and tests; `PageAuditListItem{id,url,score,previous_score,created_at}` identical in route helper, schema, TS; action names in Task 6 match usage in Tasks 6-7 components.
