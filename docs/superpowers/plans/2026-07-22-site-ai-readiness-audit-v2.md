# Site AI-Readiness Audit v2 + Toolkit Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the three-signal toolkit verification into a full 19-check website AI-readiness audit with history + delta, and expand the toolkit with an llms-full.txt generator and richer schema.json (Service + BreadcrumbList).

**Architecture:** New `site_audit_service` runs 19 pass/warn/fail/unknown checks (≤5 outbound URLs, SSRF-guarded, ThreadPoolExecutor fan-out like `ai_readiness_service`), persists each run to a new `site_audits` table for trend/delta. New admin-only API routes under `/clients/{id}/site-audit`. Toolkit gains a 4th file (llms-full.txt, own generate endpoint) and schema.json prompt v5. Frontend adds an audit card on the toolkit page and a per-competitor "Full audit" button on the competitors page, sharing one results component.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), BeautifulSoup + httpx via `url_safety.safe_get`, Claude Haiku via `claude_client`, Next.js 15 + shadcn/ui (frontend).

**Spec:** `docs/superpowers/specs/2026-07-11-site-ai-readiness-audit-v2-design.md`

## Global Constraints

- **No score formula change.** Technical Foundations / Structured Data keep existing behavior; the audit is informational; llms-full verification never touches dimension scores. No SCORE_VERSION bump.
- **Language rules (CLAUDE.md §2)** on every check label/detail/fix — they land in the Phase 5 client report. Never "cited/mentioned/citation"; plain English, no jargon. Fix strings are literal constants, not Claude-generated.
- **Max 4 content URLs per audit run** (homepage, robots.txt, sitemap.xml, llms.txt + llms-full.txt) plus one no-redirect http:// probe. Timeout 10s each. Every fetch through `is_safe_crawl_url` / `safe_get`.
- **Competitor audits are live-only, never persisted.** A competitor's results never feed the client's score.
- **Admin-only** (existing bearer auth). Client view (`/view/*`) gets nothing in this phase. No new nav page (CLAUDE.md §9 untouched).
- **RLS enabled inline** in the same migration for the new table (seenby-migrations skill).
- Current single alembic head is `e5f0a7b4c9d3` — the new migration's `down_revision`.
- Frontend: shadcn/ui only; all fetches via `src/lib/api.ts`; all types in `src/types/index.ts`.
- On-demand only — no scheduled audits.
- Backend tests: `poetry run pytest` from `backend/` (poetry at `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe` on this machine).

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/site_audit.py` (new) | `SiteAudit` row: checks JSON + denormalized summary counts |
| `backend/alembic/versions/<generated>_add_site_audits_and_llms_full.py` (new) | site_audits table (RLS on) + toolkit_files 2 new columns |
| `backend/app/services/site_audit_service.py` (new) | 19 checks, fetch fan-out, summarize, persist, delta |
| `backend/app/services/verification_crawler.py` | + `verify_llms_full_txt`, `verify_all` returns 4th key |
| `backend/app/services/ai_readiness_service.py` | JSON-LD parsing refactored into reusable helpers; `competitor_id` passthrough |
| `backend/app/services/toolkit_service.py` | + `generate_llms_full_txt` |
| `backend/app/prompts/toolkit.py` | + `build_llms_full_txt`; `build_schema_json` v5 (Service + BreadcrumbList) |
| `backend/app/api/v1/site_audit.py` (new) | run / latest / competitor routes |
| `backend/app/api/v1/toolkit.py` | + generate-llms-full route; verify persists 4th flag |
| `backend/app/schemas/site_audit.py` (new) | response schemas |
| `backend/app/schemas/toolkit.py`, `backend/app/schemas/ai_readiness.py` | additive fields |
| `frontend/src/components/SiteAuditResults.tsx` (new) | shared grouped-results view (toolkit card + competitor inline) |
| `frontend/src/components/clients/SiteAuditCard.tsx` (new) | Run button + results + delta line on toolkit page |
| `frontend/src/app/clients/[id]/toolkit/*` | 4th file card, audit card wiring |
| `frontend/src/components/competitors/AIReadinessSection.tsx` | per-competitor "Full audit" button |

---

### Task 1: SiteAudit model + ToolkitFiles columns + migration

**Files:**
- Create: `backend/app/models/site_audit.py`
- Modify: `backend/app/models/toolkit_files.py`
- Modify: `backend/tests/conftest.py:9` (model import list)
- Create: `backend/alembic/versions/<generated>_add_site_audits_and_llms_full.py`
- Test: `backend/tests/test_site_audit_model.py`

**Interfaces:**
- Produces: `SiteAudit` model (`id, client_id, checks: list, passed, warned, failed, unknown, created_at`); `ToolkitFiles.llms_full_txt: str | None`, `ToolkitFiles.llms_full_verified: bool`.

- [ ] **Step 1: Write the failing model test**

`backend/tests/test_site_audit_model.py`:

```python
import uuid


def _make_client(db):
    from app.models.client import Client
    c = Client(
        name="Acme Dental",
        website="https://acme.com",
        industry="Dental clinic",
        contact_email="hello@acme.com",
    )
    db.add(c)
    db.commit()
    return c


def test_site_audit_round_trip(db):
    from app.models.site_audit import SiteAudit
    client = _make_client(db)
    checks = [
        {"id": "https", "label": "Secure connection (HTTPS)", "status": "pass",
         "detail": "Your site is served over a secure connection.", "fix": ""},
    ]
    audit = SiteAudit(client_id=client.id, checks=checks, passed=1, warned=0, failed=0, unknown=0)
    db.add(audit)
    db.commit()

    row = db.query(SiteAudit).one()
    assert row.client_id == client.id
    assert row.checks[0]["id"] == "https"
    assert (row.passed, row.warned, row.failed, row.unknown) == (1, 0, 0, 0)
    assert row.created_at is not None


def test_toolkit_files_llms_full_columns_default(db):
    from app.models.toolkit_files import ToolkitFiles
    client = _make_client(db)
    tf = ToolkitFiles(client_id=client.id, llms_txt="x", schema_json="{}", robots_txt="y")
    db.add(tf)
    db.commit()
    row = db.query(ToolkitFiles).one()
    assert row.llms_full_txt is None
    assert row.llms_full_verified is False
```

Note: if `Client(...)` above fails with a NOT NULL error on another column, open `backend/app/models/client.py` and supply the minimal extra required fields — copy how `tests/test_guarantee_model.py` builds its client.

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/test_site_audit_model.py -q` (from `backend/`)
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.site_audit'`

- [ ] **Step 3: Create the model and columns**

`backend/app/models/site_audit.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class SiteAudit(Base):
    """One persisted run of the 19-check site AI-readiness audit.

    Every run inserts a new row — history is the point (Phase 5's monthly
    report reads latest-vs-previous for its technical-delta section).
    Competitor audits are live-only and never write here. See
    docs/superpowers/specs/2026-07-11-site-ai-readiness-audit-v2-design.md.
    """

    __tablename__ = "site_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Full list of check dicts: {"id","label","status","detail","fix"}
    checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

In `backend/app/models/toolkit_files.py`, after the `robots_verified` line add:

```python
    # llms-full.txt is optional and added after the original three files —
    # nullable because existing rows predate it (UI shows "Generate" when null).
    # Its verification NEVER touches dimension scores (spec §6).
    llms_full_txt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llms_full_verified: Mapped[bool] = mapped_column(Boolean, default=False)
```

In `backend/tests/conftest.py` line 9, add `site_audit` to the model import list (before the `# noqa`):

```python
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot, control_query, guarantee, site_audit  # noqa: F401
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/test_site_audit_model.py -q`
Expected: 2 passed

- [ ] **Step 5: Create the migration**

Run: `poetry run alembic revision -m "add site audits and llms full"` (from `backend/`). This generates a file with a fresh unique revision ID — keep that ID, replace the file's body so it reads (substituting `<generated>` with the ID alembic created):

```python
"""add site audits and llms full

Revision ID: <generated>
Revises: e5f0a7b4c9d3
Create Date: <keep generated date>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '<generated>'
down_revision: Union[str, None] = 'e5f0a7b4c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_audits_client_id", "site_audits", ["client_id"])
    op.execute("ALTER TABLE site_audits ENABLE ROW LEVEL SECURITY;")
    op.add_column("toolkit_files", sa.Column("llms_full_txt", sa.Text(), nullable=True))
    op.add_column(
        "toolkit_files",
        sa.Column("llms_full_verified", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("toolkit_files", "llms_full_verified")
    op.drop_column("toolkit_files", "llms_full_txt")
    op.execute("ALTER TABLE site_audits DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_site_audits_client_id", table_name="site_audits")
    op.drop_table("site_audits")
```

- [ ] **Step 6: Verify the migration chain (seenby-migrations gate)**

Run from `backend/`:

```bash
poetry run alembic heads
```
Expected: exactly ONE head — the new revision ID.

```bash
grep -rn "^revision" alembic/versions/ | sort | uniq -d -f1
```
Expected: no output (no duplicate IDs).

⚠️ `backend/.env`'s `DATABASE_URL` points at the **prod Supabase** database. Do NOT run `alembic upgrade head` in this task — prod migration happens only via the seenby-release runbook after merge.

- [ ] **Step 7: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass (646+ tests).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/site_audit.py backend/app/models/toolkit_files.py backend/tests/conftest.py backend/tests/test_site_audit_model.py backend/alembic/versions/
git commit -m "feat(site-audit): SiteAudit model + toolkit_files llms-full columns + migration"
```

---

### Task 2: Crawler + JSON-LD helpers

**Files:**
- Modify: `backend/app/services/verification_crawler.py`
- Modify: `backend/app/services/ai_readiness_service.py`
- Test: `backend/tests/test_verification_crawler.py` (append; create if missing), `backend/tests/test_ai_readiness_service.py` (append)

**Interfaces:**
- Produces: `verify_llms_full_txt(website: str) -> bool`; `verify_all(website) -> dict` now returns 4 keys (`llms_verified, schema_verified, robots_verified, llms_full_verified`); `parse_jsonld_scripts(html: str) -> list[dict]`; `jsonld_types_from(items: list[dict]) -> list[str]` (both in `ai_readiness_service`).
- Consumes: existing `_domain_base`, `safe_get`, `is_safe_crawl_url`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_ai_readiness_service.py`:

```python
# ── JSON-LD parsing helpers ──────────────────────────────────────────────────

def test_parse_jsonld_scripts_flattens_graph():
    from app.services.ai_readiness_service import parse_jsonld_scripts
    html = ('<html><head><script type="application/ld+json">'
            '{"@context": "https://schema.org", "@graph": ['
            '{"@type": "Organization", "name": "Acme"},'
            '{"@type": "FAQPage"}]}</script></head></html>')
    items = parse_jsonld_scripts(html)
    assert len(items) == 2
    assert items[0]["@type"] == "Organization"


def test_parse_jsonld_scripts_skips_malformed_json():
    from app.services.ai_readiness_service import parse_jsonld_scripts
    html = ('<script type="application/ld+json">{not json}</script>'
            '<script type="application/ld+json">{"@type": "WebSite"}</script>')
    items = parse_jsonld_scripts(html)
    assert len(items) == 1


def test_jsonld_types_from_handles_type_lists():
    from app.services.ai_readiness_service import jsonld_types_from
    types = jsonld_types_from([{"@type": ["Dentist", "LocalBusiness"]}, {"@type": "WebSite"}, {}])
    assert types == ["Dentist", "LocalBusiness", "WebSite"]
```

Append to `backend/tests/test_verification_crawler.py` (if this file doesn't exist, create it with the imports shown; follow the `_resp` fixture style used in `test_ai_readiness_service.py` — a helper returning an object with `.status_code` and `.text`):

```python
from unittest.mock import patch

from app.services.verification_crawler import verify_all, verify_llms_full_txt


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_verify_llms_full_txt_true_on_200_nonempty():
    with patch("app.services.verification_crawler.is_safe_crawl_url", return_value=True), \
         patch("app.services.verification_crawler.safe_get", return_value=_Resp(200, "# Acme full")):
        assert verify_llms_full_txt("https://acme.com") is True


def test_verify_llms_full_txt_false_on_404_or_empty():
    with patch("app.services.verification_crawler.is_safe_crawl_url", return_value=True), \
         patch("app.services.verification_crawler.safe_get", return_value=_Resp(404)):
        assert verify_llms_full_txt("https://acme.com") is False
    with patch("app.services.verification_crawler.is_safe_crawl_url", return_value=True), \
         patch("app.services.verification_crawler.safe_get", return_value=_Resp(200, "   ")):
        assert verify_llms_full_txt("https://acme.com") is False


def test_verify_all_returns_four_keys():
    with patch("app.services.verification_crawler.verify_llms_txt", return_value=True), \
         patch("app.services.verification_crawler.verify_schema_json", return_value=False), \
         patch("app.services.verification_crawler.verify_robots_txt", return_value=True), \
         patch("app.services.verification_crawler.verify_llms_full_txt", return_value=False):
        result = verify_all("https://acme.com")
    assert result == {
        "llms_verified": True,
        "schema_verified": False,
        "robots_verified": True,
        "llms_full_verified": False,
    }
```

Note: patching module-level names called from `verify_all` requires `verify_all` to call them unqualified (it does — same module).

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_verification_crawler.py tests/test_ai_readiness_service.py -q`
Expected: FAIL — `ImportError` on `verify_llms_full_txt` / `parse_jsonld_scripts`.

- [ ] **Step 3: Implement**

In `backend/app/services/verification_crawler.py`, after `verify_llms_txt` add:

```python
def verify_llms_full_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/llms-full.txt"
        if not is_safe_crawl_url(url):
            return False
        r = safe_get(url, timeout=_TIMEOUT)
        return r.status_code == 200 and len(r.text.strip()) > 0
    except Exception:
        return False
```

Replace `verify_all` with:

```python
def verify_all(website: str) -> dict[str, bool]:
    return {
        "llms_verified": verify_llms_txt(website),
        "schema_verified": verify_schema_json(website),
        "robots_verified": verify_robots_txt(website),
        # Informational only — never drives a dimension score (spec §6).
        "llms_full_verified": verify_llms_full_txt(website),
    }
```

In `backend/app/services/ai_readiness_service.py`, replace the body of `check_homepage_schema` by extracting two module-level helpers (place them right above `check_homepage_schema`):

```python
def parse_jsonld_scripts(html: str) -> list[dict]:
    """Parsed JSON-LD items in <script type="application/ld+json"> tags.

    Flattens @graph containers, skips malformed JSON and non-dict items.
    Shared by the competitor readiness check and site_audit_service.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        found = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        found = found if isinstance(found, list) else [found]
        items.extend(i for i in found if isinstance(i, dict))
    return items


def jsonld_types_from(items: list[dict]) -> list[str]:
    types: list[str] = []
    for item in items:
        t = item.get("@type")
        if isinstance(t, str):
            types.append(t)
        elif isinstance(t, list):
            types.extend(x for x in t if isinstance(x, str))
    return types


def check_homepage_schema(website: str) -> list[str]:
    """@type values found in JSON-LD on the homepage.

    Empty list when there's none, the markup is malformed, or the fetch fails.
    """
    try:
        url = _domain_base(website)
        if not is_safe_crawl_url(url):
            return []
        r = safe_get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        return jsonld_types_from(parse_jsonld_scripts(r.text))
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass (incl. no regressions)**

Run: `poetry run pytest tests/test_verification_crawler.py tests/test_ai_readiness_service.py tests/test_api_toolkit.py tests/test_toolkit_service.py -q`
Expected: all pass. (`test_api_toolkit.py::test_verify_returns_verification_results` patches `verify_all` wholesale, so the 4th key doesn't break it — confirm.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/verification_crawler.py backend/app/services/ai_readiness_service.py backend/tests/test_verification_crawler.py backend/tests/test_ai_readiness_service.py
git commit -m "feat(site-audit): verify_llms_full_txt + reusable JSON-LD parsing helpers"
```

---

### Task 3: site_audit_service — the 19 checks

**Files:**
- Create: `backend/app/services/site_audit_service.py`
- Test: `backend/tests/test_site_audit_service.py`

**Interfaces:**
- Produces: `run_site_audit(website: str) -> list[dict]` (always exactly 19 dicts `{"id","label","status","detail","fix"}`, statuses `"pass"|"warn"|"fail"|"unknown"`); `summarize(checks: list[dict]) -> dict` (`{"passed": int, "warned": int, "failed": int, "unknown": int}`). Check ids, in order: `robots_exists, robots_ai_bots, llms_txt, llms_full_txt, https, sitemap_exists, sitemap_urls, sitemap_fresh, title, meta_description, canonical, open_graph, h1, heading_order, viewport, internal_links, response_time, jsonld_present, jsonld_types`.
- Consumes: `_parse_robots_groups`, `_is_agent_blocked`, `parse_jsonld_scripts`, `jsonld_types_from` from `ai_readiness_service`; `_domain_base` from `verification_crawler`; `safe_get`, `is_safe_crawl_url` from `url_safety`; `AI_CRAWLER_BOTS` from constants; `_INDUSTRY_SCHEMA_TYPES` from `app.prompts.toolkit`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_site_audit_service.py`:

```python
"""site_audit_service tests — mocked safe_get with HTML/XML fixtures (spec §10)."""
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import pytest

from app.services.url_safety import SafeResponse

_RECENT = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d")
_STALE = (datetime.now(UTC) - timedelta(days=300)).strftime("%Y-%m-%d")

HEALTHY_HTML = (
    "<html><head>"
    "<title>Acme Dental Clinic Kuala Lumpur</title>"
    '<meta name="description" content="Acme Dental Clinic provides gentle, affordable dental care '
    'for families in Kuala Lumpur, from checkups to braces and implants.">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<link rel="canonical" href="https://acme.com/">'
    '<meta property="og:title" content="Acme Dental Clinic">'
    '<meta property="og:description" content="Gentle dental care in KL">'
    '<meta property="og:image" content="https://acme.com/logo.png">'
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": "Acme"}]}'
    "</script></head><body>"
    "<h1>Welcome to Acme Dental</h1><h2>Our Services</h2><h3>Braces</h3><h2>Contact</h2>"
    + "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(12))
    + "</body></html>"
)

HEALTHY_ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://acme.com/sitemap.xml\n"

HEALTHY_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<url><loc>https://acme.com/</loc><lastmod>{_RECENT}</lastmod></url>"
    "<url><loc>https://acme.com/services</loc></url>"
    "</urlset>"
)

SITEMAP_INDEX_STALE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<sitemap><loc>https://acme.com/sitemap-pages.xml</loc><lastmod>{_STALE}</lastmod></sitemap>"
    "</sitemapindex>"
)

BLOCKING_ROBOTS = (
    "User-agent: GPTBot\nDisallow: /\n\n"
    "User-agent: ClaudeBot\nDisallow: /\n\n"
    "User-agent: *\nAllow: /\n\nSitemap: https://acme.com/sitemap.xml\n"
)

_HEALTHY_ROUTES = {
    "/": SafeResponse(200, HEALTHY_HTML),
    "/robots.txt": SafeResponse(200, HEALTHY_ROBOTS),
    "/llms.txt": SafeResponse(200, "# Acme Dental Clinic\n> Gentle dental care"),
    "/llms-full.txt": SafeResponse(200, "# Acme Dental Clinic — full\ndetails"),
    "/sitemap.xml": SafeResponse(200, HEALTHY_SITEMAP),
}


def _fake_safe_get(routes):
    def _get(url, **kwargs):
        path = urlparse(url).path or "/"
        result = routes.get(path, SafeResponse(404))
        if isinstance(result, Exception):
            raise result
        return result
    return _get


def _run(routes, http_redirects=True):
    from app.services import site_audit_service
    with patch.object(site_audit_service, "is_safe_crawl_url", return_value=True), \
         patch.object(site_audit_service, "safe_get", side_effect=_fake_safe_get(routes)), \
         patch.object(site_audit_service, "_http_redirects_to_https", return_value=http_redirects):
        return site_audit_service.run_site_audit("https://acme.com")


def _by_id(checks):
    return {c["id"]: c for c in checks}


# 1. Fully healthy fixture site → 19 passes.
def test_healthy_site_all_19_pass():
    checks = _run(_HEALTHY_ROUTES)
    assert len(checks) == 19
    non_pass = [c["id"] for c in checks if c["status"] != "pass"]
    assert non_pass == []
    # every check carries the full shape
    for c in checks:
        assert set(c) == {"id", "label", "status", "detail", "fix"}
        assert c["fix"] == ""  # empty when pass


# 2. robots.txt disallowing GPTBot + ClaudeBot → robots_ai_bots fail names both bots.
def test_blocked_bots_named_in_fail():
    routes = dict(_HEALTHY_ROUTES)
    routes["/robots.txt"] = SafeResponse(200, BLOCKING_ROBOTS)
    c = _by_id(_run(routes))["robots_ai_bots"]
    assert c["status"] == "fail"
    assert "GPTBot" in c["detail"] and "ClaudeBot" in c["detail"]
    assert c["fix"] != ""


# 3. Missing sitemap, missing canonical, two H1s, no viewport → correct statuses + fixes.
def test_degraded_page_statuses_and_fixes():
    degraded_html = (
        "<html><head><title>Acme Dental Clinic Kuala Lumpur</title>"
        '<meta name="description" content="Acme Dental Clinic provides gentle, affordable dental '
        'care for families in Kuala Lumpur, from checkups to braces and implants.">'
        "</head><body><h1>One</h1><h1>Two</h1></body></html>"
    )
    routes = dict(_HEALTHY_ROUTES)
    routes["/"] = SafeResponse(200, degraded_html)
    routes["/sitemap.xml"] = SafeResponse(404)
    by = _by_id(_run(routes))
    assert by["sitemap_exists"]["status"] == "fail" and by["sitemap_exists"]["fix"] != ""
    assert by["sitemap_urls"]["status"] == "unknown"
    assert by["sitemap_fresh"]["status"] == "unknown"
    assert by["canonical"]["status"] == "warn" and by["canonical"]["fix"] != ""
    assert by["h1"]["status"] == "warn"
    assert by["viewport"]["status"] == "fail" and by["viewport"]["fix"] != ""


# 4. Homepage timeout → Groups C/D all unknown, A/B unaffected.
def test_homepage_timeout_poisons_only_c_and_d():
    routes = dict(_HEALTHY_ROUTES)
    routes["/"] = httpx.TimeoutException("boom")
    by = _by_id(_run(routes))
    c_d_ids = ["title", "meta_description", "canonical", "open_graph", "h1", "heading_order",
               "viewport", "internal_links", "response_time", "jsonld_present", "jsonld_types"]
    for check_id in c_d_ids:
        assert by[check_id]["status"] == "unknown", check_id
    for check_id in ["robots_exists", "robots_ai_bots", "llms_txt", "llms_full_txt",
                     "sitemap_exists", "sitemap_urls", "sitemap_fresh"]:
        assert by[check_id]["status"] == "pass", check_id


# 5. Sitemap index parses; lastmod 300 days old → warn.
def test_sitemap_index_parses_and_stale_lastmod_warns():
    routes = dict(_HEALTHY_ROUTES)
    routes["/sitemap.xml"] = SafeResponse(200, SITEMAP_INDEX_STALE)
    by = _by_id(_run(routes))
    assert by["sitemap_exists"]["status"] == "pass"
    assert by["sitemap_urls"]["status"] == "pass"
    assert by["sitemap_fresh"]["status"] == "warn"


def test_llms_full_missing_warns_never_fails():
    routes = dict(_HEALTHY_ROUTES)
    routes["/llms-full.txt"] = SafeResponse(404)
    c = _by_id(_run(routes))["llms_full_txt"]
    assert c["status"] == "warn"


def test_http_not_redirecting_warns():
    c = _by_id(_run(_HEALTHY_ROUTES, http_redirects=False))["https"]
    assert c["status"] == "warn"


def test_summarize_counts():
    from app.services.site_audit_service import summarize
    checks = [
        {"id": "a", "label": "", "status": "pass", "detail": "", "fix": ""},
        {"id": "b", "label": "", "status": "pass", "detail": "", "fix": ""},
        {"id": "c", "label": "", "status": "warn", "detail": "", "fix": "x"},
        {"id": "d", "label": "", "status": "fail", "detail": "", "fix": "x"},
        {"id": "e", "label": "", "status": "unknown", "detail": "", "fix": ""},
    ]
    assert summarize(checks) == {"passed": 2, "warned": 1, "failed": 1, "unknown": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_site_audit_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.site_audit_service'`

- [ ] **Step 3: Implement the service**

`backend/app/services/site_audit_service.py` — complete file:

```python
"""Site AI-readiness audit — 19 checks across 4 groups (spec 2026-07-11).

Informational only: NO dimension score is derived from these results
(that would bump SCORE_VERSION and is explicitly out of scope). Every
label/detail/fix string is client-facing copy (it lands in the Phase 5
monthly report) — plain English, CLAUDE.md §2 language rules, and all
fix strings are literal constants, never Claude-generated.

A crawl failure must never crash the audit or masquerade as a client
problem: any fetch/parse error yields status "unknown". The audit always
returns exactly 19 checks.
"""
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
import structlog

from app.core.constants import AI_CRAWLER_BOTS
from app.prompts.toolkit import _INDUSTRY_SCHEMA_TYPES
from app.services.ai_readiness_service import (
    _is_agent_blocked,
    _parse_robots_groups,
    jsonld_types_from,
    parse_jsonld_scripts,
)
from app.services.url_safety import is_safe_crawl_url, safe_get
from app.services.verification_crawler import _domain_base

logger = structlog.get_logger()

_TIMEOUT = 10.0
_SITEMAP_FRESH_DAYS = 180
_UNKNOWN_DETAIL = "Could not check — the site didn't respond."
# Schema @types that count as "your business info is present".
_BUSINESS_TYPES = {"Organization", "LocalBusiness"} | {t for _, t in _INDUSTRY_SCHEMA_TYPES}


def _result(check_id: str, label: str, status: str, detail: str, fix: str = "") -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


def _unknown(check_id: str, label: str) -> dict:
    return _result(check_id, label, "unknown", _UNKNOWN_DETAIL)


def _fetch(url: str):
    """SafeResponse, or None when the URL is unsafe or the fetch failed."""
    try:
        if not is_safe_crawl_url(url):
            logger.warning("site_audit_unsafe_url", url=url)
            return None
        return safe_get(url, timeout=_TIMEOUT)
    except Exception:
        return None


def _fetch_homepage(base: str):
    """(SafeResponse | None, elapsed_seconds) — simple wall-clock TTLB."""
    start = time.monotonic()
    resp = _fetch(f"{base}/")
    return resp, time.monotonic() - start


def _http_redirects_to_https(base: str) -> bool | None:
    """Does http:// redirect to https://? None = couldn't tell (not evidence).

    Single request, redirects NOT followed — so no SSRF hop risk beyond the
    already-validated host.
    """
    host = urlparse(base).netloc
    url = f"http://{host}/"
    try:
        if not is_safe_crawl_url(url):
            return None
        with httpx.Client(follow_redirects=False, timeout=_TIMEOUT) as client:
            r = client.get(url)
        if r.is_redirect:
            return r.headers.get("location", "").startswith("https://")
        return False  # http serves content without redirecting
    except Exception:
        return None  # port 80 closed etc. — fine for an https-only site


def _same_domain(href: str, base: str) -> bool:
    h = urlparse(href).netloc.lower().removeprefix("www.")
    b = urlparse(base).netloc.lower().removeprefix("www.")
    return h == "" or h == b


def _sitemap_url(base: str, robots) -> str:
    if robots is not None and robots.status_code == 200:
        for line in robots.text.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                candidate = line.partition(":")[2].strip()
                if candidate:
                    return candidate
    return f"{base}/sitemap.xml"


# ── Group A — AI crawl access ────────────────────────────────────────────────

def _group_a(robots, llms, llms_full, homepage, http_redirect) -> list[dict]:
    checks: list[dict] = []

    # 1. robots_exists
    label = "robots.txt file"
    if robots is None:
        checks.append(_unknown("robots_exists", label))
    elif robots.status_code == 200:
        checks.append(_result("robots_exists", label, "pass", "Found robots.txt at /robots.txt."))
    else:
        checks.append(_result(
            "robots_exists", label, "fail",
            f"Your site returned {robots.status_code} for /robots.txt.",
            "Add a robots.txt file at your website root that welcomes AI assistants — "
            "the SeenBy toolkit generates one ready to upload.",
        ))

    # 2. robots_ai_bots — proper per-bot parsing (not the substring check the
    # generated-file verifier uses; that one stays as-is on purpose).
    label = "AI assistants allowed"
    if robots is None:
        checks.append(_unknown("robots_ai_bots", label))
    elif robots.status_code != 200:
        checks.append(_result(
            "robots_ai_bots", label, "pass",
            "No robots.txt found, so no AI assistant is blocked from reading the site.",
        ))
    else:
        groups = _parse_robots_groups(robots.text)
        wildcard_blocked = _is_agent_blocked(groups.get("*", []))
        lower_groups = {agent.lower(): rules for agent, rules in groups.items()}
        blocked = []
        for bot in AI_CRAWLER_BOTS:
            bot_rules = lower_groups.get(bot.lower())
            if bot_rules is not None:
                if _is_agent_blocked(bot_rules):
                    blocked.append(bot)
            elif wildcard_blocked:
                blocked.append(bot)
        if blocked:
            checks.append(_result(
                "robots_ai_bots", label, "fail",
                "robots.txt blocks these AI assistants from reading the site: "
                + ", ".join(blocked) + ".",
                "Update robots.txt to allow these AI assistants — the SeenBy toolkit "
                "generates a ready-to-use file.",
            ))
        else:
            checks.append(_result(
                "robots_ai_bots", label, "pass",
                "All major AI assistants are allowed to read the site.",
            ))

    # 3. llms_txt
    label = "llms.txt file"
    if llms is None:
        checks.append(_unknown("llms_txt", label))
    elif llms.status_code == 200 and llms.text.strip():
        checks.append(_result("llms_txt", label, "pass", "Found llms.txt at /llms.txt."))
    else:
        checks.append(_result(
            "llms_txt", label, "fail",
            "No llms.txt file found — AI assistants have no summary of the business to read.",
            "Generate llms.txt with the SeenBy toolkit and upload it to the website root.",
        ))

    # 4. llms_full_txt — optional file: warn when missing, never fail.
    label = "llms-full.txt file"
    if llms_full is None:
        checks.append(_unknown("llms_full_txt", label))
    elif llms_full.status_code == 200 and llms_full.text.strip():
        checks.append(_result("llms_full_txt", label, "pass", "Found llms-full.txt at /llms-full.txt."))
    else:
        checks.append(_result(
            "llms_full_txt", label, "warn",
            "No llms-full.txt found. It's optional, but gives AI assistants a much "
            "richer picture of the business.",
            "Generate llms-full.txt with the SeenBy toolkit and upload it next to llms.txt.",
        ))

    # 5. https
    label = "Secure connection (HTTPS)"
    if homepage is None:
        checks.append(_unknown("https", label))
    elif homepage.status_code >= 400:
        checks.append(_result(
            "https", label, "fail",
            f"The homepage returned an error ({homepage.status_code}).",
            "Get the homepage loading correctly — AI assistants can't read a page that errors.",
        ))
    elif http_redirect is False:
        checks.append(_result(
            "https", label, "warn",
            "The site works over a secure connection, but the insecure http:// address "
            "doesn't redirect visitors to it.",
            "Ask your web host to redirect http:// to https:// automatically.",
        ))
    else:
        checks.append(_result(
            "https", label, "pass", "The site is served over a secure connection.",
        ))

    return checks


# ── Group B — Sitemap ────────────────────────────────────────────────────────

def _group_b(sitemap, sitemap_url: str) -> list[dict]:
    checks: list[dict] = []
    labels = {
        "sitemap_exists": "Sitemap file",
        "sitemap_urls": "Sitemap lists your pages",
        "sitemap_fresh": "Sitemap freshness",
    }

    root = None
    if sitemap is not None and sitemap.status_code == 200:
        try:
            candidate = ET.fromstring(sitemap.text)
            if candidate.tag.endswith("urlset") or candidate.tag.endswith("sitemapindex"):
                root = candidate
        except ET.ParseError:
            root = None

    # 6. sitemap_exists
    if sitemap is None:
        checks.append(_unknown("sitemap_exists", labels["sitemap_exists"]))
    elif root is not None:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "pass",
            f"Found a valid sitemap at {sitemap_url}.",
        ))
    elif sitemap.status_code == 200:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "fail",
            f"The file at {sitemap_url} isn't a valid sitemap.",
            "Regenerate the sitemap — most website platforms and SEO plugins can "
            "produce a valid sitemap.xml automatically.",
        ))
    else:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "fail",
            f"No sitemap found (checked {sitemap_url}).",
            "Publish a sitemap.xml at the website root and list it in robots.txt — "
            "it's how AI systems discover all your pages.",
        ))

    if root is None:
        skip = "Skipped — no valid sitemap to inspect."
        checks.append(_result("sitemap_urls", labels["sitemap_urls"], "unknown", skip))
        checks.append(_result("sitemap_fresh", labels["sitemap_fresh"], "unknown", skip))
        return checks

    # 7. sitemap_urls
    locs = [el for el in root.iter() if el.tag.endswith("loc")]
    if locs:
        checks.append(_result(
            "sitemap_urls", labels["sitemap_urls"], "pass",
            f"The sitemap lists {len(locs)} page{'s' if len(locs) != 1 else ''}.",
        ))
    else:
        checks.append(_result(
            "sitemap_urls", labels["sitemap_urls"], "fail",
            "The sitemap exists but lists no pages.",
            "Regenerate the sitemap so it includes every page you want AI systems to know about.",
        ))

    # 8. sitemap_fresh
    dates = []
    for el in root.iter():
        if el.tag.endswith("lastmod") and el.text:
            raw = el.text.strip()
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(raw[:10])
                except ValueError:
                    continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            dates.append(parsed)
    if not dates:
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "warn",
            "The sitemap has no dates, so AI systems can't tell how fresh your content is.",
            "Add <lastmod> dates to the sitemap — most sitemap generators include them automatically.",
        ))
    elif max(dates) >= datetime.now(UTC) - timedelta(days=_SITEMAP_FRESH_DAYS):
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "pass",
            f"The sitemap was updated within the last {_SITEMAP_FRESH_DAYS} days.",
        ))
    else:
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "warn",
            f"The newest date in the sitemap is more than {_SITEMAP_FRESH_DAYS} days old — "
            "the site looks inactive to AI systems.",
            "Publish or update content, then regenerate the sitemap so its dates reflect it.",
        ))
    return checks


# ── Group C — Homepage content signals ───────────────────────────────────────

_C_LABELS = {
    "title": "Page title",
    "meta_description": "Page description",
    "canonical": "Preferred page address (canonical)",
    "open_graph": "Link preview info (Open Graph)",
    "h1": "Main headline (H1)",
    "heading_order": "Heading structure",
    "viewport": "Mobile-friendly setup",
    "internal_links": "Links between your pages",
    "response_time": "Homepage speed",
}


def _group_c(soup, base: str, elapsed: float) -> list[dict]:
    if soup is None:
        return [_unknown(check_id, label) for check_id, label in _C_LABELS.items()]
    checks: list[dict] = []

    # 9. title — 10–70 chars pass; present but outside range warn; missing fail.
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    if not title:
        checks.append(_result(
            "title", _C_LABELS["title"], "fail",
            "The homepage has no title.",
            "Add a <title> of 10–70 characters that names the business and what it does.",
        ))
    elif 10 <= len(title) <= 70:
        checks.append(_result("title", _C_LABELS["title"], "pass", f'Title found ({len(title)} characters): "{title}".'))
    else:
        checks.append(_result(
            "title", _C_LABELS["title"], "warn",
            f"The title is {len(title)} characters — outside the recommended 10–70 range.",
            "Rewrite the title to 10–70 characters, leading with the business name and main service.",
        ))

    # 10. meta_description — 50–170 chars pass; outside warn; missing fail.
    md_tag = soup.find("meta", attrs={"name": "description"})
    md = (md_tag.get("content") or "").strip() if md_tag else ""
    if not md:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "fail",
            "The homepage has no description tag.",
            "Add a meta description of 50–170 characters summarising what the business "
            "offers and where — AI assistants often quote it directly.",
        ))
    elif 50 <= len(md) <= 170:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "pass",
            f"Description found ({len(md)} characters).",
        ))
    else:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "warn",
            f"The description is {len(md)} characters — outside the recommended 50–170 range.",
            "Rewrite the meta description to 50–170 characters.",
        ))

    # 11. canonical — missing warn; cross-domain fail; same-domain pass.
    canon = soup.find("link", rel="canonical")
    href = (canon.get("href") or "").strip() if canon else ""
    if not href:
        checks.append(_result(
            "canonical", _C_LABELS["canonical"], "warn",
            "The homepage doesn't declare its preferred address.",
            'Add <link rel="canonical" href="…"> pointing at the homepage\'s own address '
            "so AI systems know which version to trust.",
        ))
    elif _same_domain(href, base):
        checks.append(_result("canonical", _C_LABELS["canonical"], "pass", f"Preferred address declared: {href}."))
    else:
        checks.append(_result(
            "canonical", _C_LABELS["canonical"], "fail",
            f"The preferred address points at a different site: {href}.",
            "Point the canonical link at this site's own homepage address.",
        ))

    # 12. open_graph — og:title + og:description pass; og:image is a detail note only.
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_title and og_desc:
        image_note = " A preview image is set too." if og_image else " No preview image (og:image) is set."
        checks.append(_result(
            "open_graph", _C_LABELS["open_graph"], "pass",
            "Link preview title and description are set." + image_note,
        ))
    else:
        checks.append(_result(
            "open_graph", _C_LABELS["open_graph"], "warn",
            "The homepage is missing link preview tags (og:title / og:description).",
            "Add Open Graph title and description tags so shared links and AI answers "
            "show a clean preview of the business.",
        ))

    # 13. h1 — exactly one pass; none fail; more than one warn.
    h1s = soup.find_all("h1")
    if len(h1s) == 1:
        checks.append(_result("h1", _C_LABELS["h1"], "pass", "The homepage has exactly one main headline."))
    elif len(h1s) == 0:
        checks.append(_result(
            "h1", _C_LABELS["h1"], "fail",
            "The homepage has no main headline (H1).",
            "Add one H1 that states the business name and what it does.",
        ))
    else:
        checks.append(_result(
            "h1", _C_LABELS["h1"], "warn",
            f"The homepage has {len(h1s)} main headlines — there should be exactly one.",
            "Keep one H1 and turn the others into H2 subheadings.",
        ))

    # 14. heading_order — no skipped levels in the first 20 headings; warn only.
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])[:20]
    prev_level = 0
    skipped = False
    for h in headings:
        level = int(h.name[1])
        if prev_level and level > prev_level + 1:
            skipped = True
            break
        prev_level = level
    if skipped:
        checks.append(_result(
            "heading_order", _C_LABELS["heading_order"], "warn",
            "Headings skip levels (for example jumping from H2 straight to H4), which "
            "makes the page structure harder for AI systems to follow.",
            "Keep headings in order: H1, then H2 sections, then H3 details within them.",
        ))
    else:
        checks.append(_result(
            "heading_order", _C_LABELS["heading_order"], "pass",
            "Headings are in a clean, logical order.",
        ))

    # 15. viewport — mobile-friendliness proxy.
    if soup.find("meta", attrs={"name": "viewport"}):
        checks.append(_result("viewport", _C_LABELS["viewport"], "pass", "The page is set up for mobile screens."))
    else:
        checks.append(_result(
            "viewport", _C_LABELS["viewport"], "fail",
            "The page has no mobile viewport tag — it may render poorly on phones.",
            'Add <meta name="viewport" content="width=device-width, initial-scale=1"> '
            "to the page head.",
        ))

    # 16. internal_links — ≥10 same-domain links pass; below warn.
    count = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if _same_domain(href, base):
            count += 1
    if count >= 10:
        checks.append(_result(
            "internal_links", _C_LABELS["internal_links"], "pass",
            f"The homepage links to {count} of your own pages.",
        ))
    else:
        checks.append(_result(
            "internal_links", _C_LABELS["internal_links"], "warn",
            f"The homepage links to only {count} of your own pages.",
            "Link from the homepage to your key service pages so AI systems can find them.",
        ))

    # 17. response_time — wall-clock on the homepage fetch. <2s pass, 2–5s warn, >5s fail.
    if elapsed < 2:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "pass",
            f"The homepage responded in {elapsed:.1f}s.",
        ))
    elif elapsed <= 5:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "warn",
            f"The homepage took {elapsed:.1f}s to respond — slower than the 2s target.",
            "Ask your web host or developer about speeding the site up (caching, image "
            "compression, better hosting).",
        ))
    else:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "fail",
            f"The homepage took {elapsed:.1f}s to respond.",
            "A page this slow gets skipped. Ask your web host or developer about caching "
            "and hosting upgrades.",
        ))
    return checks


# ── Group D — Structured data ────────────────────────────────────────────────

_D_LABELS = {
    "jsonld_present": "Structured data present",
    "jsonld_types": "Business info in structured data",
}


def _group_d(soup, html: str | None) -> list[dict]:
    if soup is None or html is None:
        return [_unknown(check_id, label) for check_id, label in _D_LABELS.items()]
    checks: list[dict] = []
    items = parse_jsonld_scripts(html)
    types = jsonld_types_from(items)

    # 18. jsonld_present
    if items:
        checks.append(_result(
            "jsonld_present", _D_LABELS["jsonld_present"], "pass",
            f"Found {len(items)} structured data entr{'ies' if len(items) != 1 else 'y'} on the homepage.",
        ))
    else:
        checks.append(_result(
            "jsonld_present", _D_LABELS["jsonld_present"], "fail",
            "No structured data found on the homepage.",
            "Add schema.org structured data — the SeenBy toolkit generates a schema.json "
            "file with everything AI systems need.",
        ))

    # 19. jsonld_types — pass when a business-type entry is present.
    if types and set(types) & _BUSINESS_TYPES:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "pass",
            "Business details are present in structured data. Types found: " + ", ".join(sorted(set(types))) + ".",
        ))
    elif types:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "warn",
            "Structured data exists but doesn't describe the business itself. Types found: "
            + ", ".join(sorted(set(types))) + ".",
            "Add an Organization or LocalBusiness entry — the SeenBy toolkit's schema.json includes one.",
        ))
    else:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "warn",
            "No business details in structured data, so AI systems can't confirm who you are.",
            "Add an Organization or LocalBusiness entry — the SeenBy toolkit's schema.json includes one.",
        ))
    return checks


# ── Entry points ─────────────────────────────────────────────────────────────

def run_site_audit(website: str) -> list[dict]:
    """Run all 19 checks against a website. Always returns exactly 19 dicts."""
    from bs4 import BeautifulSoup  # local import keeps module import light

    base = _domain_base(website)
    with ThreadPoolExecutor(max_workers=5) as pool:
        robots_f = pool.submit(_fetch, f"{base}/robots.txt")
        llms_f = pool.submit(_fetch, f"{base}/llms.txt")
        llms_full_f = pool.submit(_fetch, f"{base}/llms-full.txt")
        home_f = pool.submit(_fetch_homepage, base)
        http_f = pool.submit(_http_redirects_to_https, base)
        robots = robots_f.result()
        llms = llms_f.result()
        llms_full = llms_full_f.result()
        homepage, elapsed = home_f.result()
        http_redirect = http_f.result()

    # Sitemap URL can come from robots.txt, so this fetch happens after.
    sm_url = _sitemap_url(base, robots)
    sitemap = _fetch(sm_url)

    homepage_ok = homepage is not None and homepage.status_code == 200
    soup = BeautifulSoup(homepage.text, "html.parser") if homepage_ok else None
    html = homepage.text if homepage_ok else None

    checks: list[dict] = []
    checks += _group_a(robots, llms, llms_full, homepage, http_redirect)
    checks += _group_b(sitemap, sm_url)
    checks += _group_c(soup, base, elapsed)
    checks += _group_d(soup, html)
    return checks


def summarize(checks: list[dict]) -> dict:
    return {
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "warned": sum(1 for c in checks if c["status"] == "warn"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
        "unknown": sum(1 for c in checks if c["status"] == "unknown"),
    }
```

Implementation notes for the engineer:
- `SafeResponse` import in tests comes from `app.services.url_safety` — it's a plain dataclass `(status_code, text, headers)`.
- The homepage-error case: `homepage.status_code >= 400` → Group A's `https` check fails, and `soup`/`html` are `None`, so C/D go `unknown` (spec §9: homepage failure poisons only C/D).
- `_group_c` receives `elapsed` even when the fetch failed, but returns all-unknown in that case — `response_time` is deliberately `unknown` on a failed fetch (spec: unknown = fetch failed, never masquerade as a client problem).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_site_audit_service.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/site_audit_service.py backend/tests/test_site_audit_service.py
git commit -m "feat(site-audit): 19-check site audit service with fan-out fetching"
```

---

### Task 4: Persistence + delta

**Files:**
- Modify: `backend/app/services/site_audit_service.py` (append)
- Test: `backend/tests/test_site_audit_service.py` (append)

**Interfaces:**
- Produces: `compute_delta(latest: list[dict], previous: list[dict]) -> dict` (`{"fixed": [ids], "regressed": [ids]}`); `run_and_persist_site_audit(client_id: uuid.UUID, website: str, db: Session) -> SiteAudit`; `get_latest_with_delta(client_id: uuid.UUID, db: Session) -> dict | None` (`{"audit": SiteAudit, "fixed": [...], "regressed": [...], "has_previous": bool}`).
- Consumes: Task 1's `SiteAudit` model; Task 3's `run_site_audit` + `summarize`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_site_audit_service.py`:

```python
# ── Delta + persistence ──────────────────────────────────────────────────────

def _check(check_id, status):
    return {"id": check_id, "label": check_id, "status": status, "detail": "", "fix": ""}


# 6. Delta computation: fail→pass shows in fixed, pass→fail in regressed.
def test_compute_delta_fixed_and_regressed():
    from app.services.site_audit_service import compute_delta
    previous = [_check("a", "fail"), _check("b", "warn"), _check("c", "pass"),
                _check("d", "pass"), _check("e", "unknown")]
    latest = [_check("a", "pass"), _check("b", "pass"), _check("c", "fail"),
              _check("d", "warn"), _check("e", "pass")]
    delta = compute_delta(latest, previous)
    assert delta["fixed"] == ["a", "b"]          # fail/warn → pass
    assert delta["regressed"] == ["c", "d"]      # pass → fail/warn
    # unknown → pass is neither fixed nor regressed
    assert "e" not in delta["fixed"] and "e" not in delta["regressed"]


def test_run_and_persist_writes_row_and_activity_log(db):
    from unittest.mock import patch
    from app.models.activity_log import ActivityLog
    from app.models.site_audit import SiteAudit
    from app.services import site_audit_service
    client = _make_client(db)
    checks = [_check("https", "pass"), _check("title", "warn"), _check("h1", "fail")]
    with patch.object(site_audit_service, "run_site_audit", return_value=checks):
        audit = site_audit_service.run_and_persist_site_audit(client.id, client.website, db)
    assert audit.id is not None
    assert (audit.passed, audit.warned, audit.failed, audit.unknown) == (1, 1, 1, 0)
    log = db.query(ActivityLog).filter(ActivityLog.client_id == client.id).one()
    assert log.event_type == "site_audit_run"
    assert db.query(SiteAudit).count() == 1


def test_get_latest_with_delta(db):
    from unittest.mock import patch
    from app.services import site_audit_service
    client = _make_client(db)
    with patch.object(site_audit_service, "run_site_audit",
                      return_value=[_check("h1", "fail")]):
        site_audit_service.run_and_persist_site_audit(client.id, client.website, db)
    with patch.object(site_audit_service, "run_site_audit",
                      return_value=[_check("h1", "pass")]):
        site_audit_service.run_and_persist_site_audit(client.id, client.website, db)
    result = site_audit_service.get_latest_with_delta(client.id, db)
    assert result["has_previous"] is True
    assert result["fixed"] == ["h1"]
    assert result["regressed"] == []
    assert result["audit"].checks[0]["status"] == "pass"


def test_get_latest_with_delta_none_when_no_audits(db):
    from app.services.site_audit_service import get_latest_with_delta
    client = _make_client(db)
    assert get_latest_with_delta(client.id, db) is None
```

Add `_make_client` at the top of the test file (same helper as Task 1's model test):

```python
def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c
```

Ordering caveat: the two persisted rows in `test_get_latest_with_delta` may share the same `created_at` second — `get_latest_with_delta` must order by `created_at.desc(), id` descending is NOT stable for UUIDs. Order by `SiteAudit.created_at.desc()` and break ties so the second insert wins; the implementation below orders on `created_at` then falls back naturally because SQLite preserves insert order for equal keys. If this test flakes, make the service order by `created_at.desc()` and, in the test, monkeypatch `created_at` on the first row to an earlier datetime before the second run.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_site_audit_service.py -q`
Expected: new tests FAIL — `AttributeError`/`ImportError` on `compute_delta` etc.; the Task 3 tests still pass.

- [ ] **Step 3: Implement**

Append to `backend/app/services/site_audit_service.py` (add `import uuid`, `from sqlalchemy.orm import Session`, `from app.models.activity_log import ActivityLog`, `from app.models.site_audit import SiteAudit` to the imports):

```python
def compute_delta(latest: list[dict], previous: list[dict]) -> dict:
    """Which check ids went fail/warn → pass (fixed) or pass → fail/warn (regressed)."""
    prev_by_id = {c["id"]: c["status"] for c in previous}
    fixed: list[str] = []
    regressed: list[str] = []
    for c in latest:
        prev = prev_by_id.get(c["id"])
        if prev in ("warn", "fail") and c["status"] == "pass":
            fixed.append(c["id"])
        elif prev == "pass" and c["status"] in ("warn", "fail"):
            regressed.append(c["id"])
    return {"fixed": fixed, "regressed": regressed}


def run_and_persist_site_audit(client_id: uuid.UUID, website: str, db: Session) -> SiteAudit:
    checks = run_site_audit(website)
    s = summarize(checks)
    audit = SiteAudit(
        client_id=client_id, checks=checks,
        passed=s["passed"], warned=s["warned"], failed=s["failed"], unknown=s["unknown"],
    )
    db.add(audit)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="site_audit_run",
        note=(
            f"Site AI-readiness audit run: {s['passed']} passed, "
            f"{s['warned']} to improve, {s['failed']} to fix."
        ),
    ))
    db.commit()
    db.refresh(audit)
    return audit


def get_latest_with_delta(client_id: uuid.UUID, db: Session) -> dict | None:
    rows = (
        db.query(SiteAudit)
        .filter(SiteAudit.client_id == client_id)
        .order_by(SiteAudit.created_at.desc())
        .limit(2)
        .all()
    )
    if not rows:
        return None
    latest = rows[0]
    if len(rows) == 2:
        delta = compute_delta(latest.checks, rows[1].checks)
        return {"audit": latest, "fixed": delta["fixed"], "regressed": delta["regressed"], "has_previous": True}
    return {"audit": latest, "fixed": [], "regressed": [], "has_previous": False}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_site_audit_service.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/site_audit_service.py backend/tests/test_site_audit_service.py
git commit -m "feat(site-audit): persist runs + fixed/regressed delta"
```

---

### Task 5: Toolkit expansion — llms-full.txt generator + schema v5

**Files:**
- Modify: `backend/app/prompts/toolkit.py`
- Modify: `backend/app/services/toolkit_service.py`
- Test: `backend/tests/test_toolkit_service.py` (append)

**Interfaces:**
- Produces: `build_llms_full_txt(client: Client) -> str` (prompt); `generate_llms_full_txt(client: Client) -> str` (Claude call, `max_tokens=4096`, service name `"toolkit_llms_full_txt"` in `record_llm_call`); `build_schema_json` now instructs 6 `@graph` entries (adds Service + BreadcrumbList), `SCHEMA_JSON_VERSION = "v5"`.
- Consumes: existing `_anthropic_client`, `_MODEL`, `_strip_code_fences`, `record_llm_call` in `toolkit_service`; `_INDUSTRY_SCHEMA_TYPES`/`_schema_type_for` in prompts.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_toolkit_service.py` (reuse the existing `_fake_client()` and `_mock_ac()` helpers already defined in this file):

```python
# ── generate_llms_full_txt ────────────────────────────────────────────────────

def test_generate_llms_full_txt_calls_claude_with_4096_tokens():
    from app.services.toolkit_service import generate_llms_full_txt
    client = _fake_client()
    mock_ac = _mock_ac("# Acme Corp — full\ndetailed content")
    with patch("app.services.toolkit_service._anthropic_client", return_value=mock_ac), \
         patch("app.services.toolkit_service.record_llm_call") as mock_record:
        result = generate_llms_full_txt(client)
    assert result.startswith("# Acme Corp")
    assert mock_ac.messages.create.call_args.kwargs["max_tokens"] == 4096
    assert mock_record.call_args.kwargs["service"] == "toolkit_llms_full_txt"


def test_generate_llms_full_txt_strips_code_fences():
    from app.services.toolkit_service import generate_llms_full_txt
    client = _fake_client()
    mock_ac = _mock_ac("```\n# Acme Corp — full\n```")
    with patch("app.services.toolkit_service._anthropic_client", return_value=mock_ac), \
         patch("app.services.toolkit_service.record_llm_call"):
        assert generate_llms_full_txt(client) == "# Acme Corp — full"


# ── llms-full + schema v5 prompts ────────────────────────────────────────────

def test_build_llms_full_txt_prompt_covers_extended_sections():
    from app.prompts.toolkit import build_llms_full_txt
    client = _fake_client()
    prompt = build_llms_full_txt(client)
    assert "Acme Corp" in prompt
    for required in ["Services", "Questions & Answers", "Policies", "Key Pages"]:
        assert required in prompt, required


def test_build_schema_json_v5_adds_service_and_breadcrumb():
    from app.prompts.toolkit import build_schema_json, SCHEMA_JSON_VERSION
    client = _fake_client()
    prompt = build_schema_json(client)
    assert SCHEMA_JSON_VERSION == "v5"
    assert "6 schemas" in prompt
    assert '"Service"' in prompt
    assert '"BreadcrumbList"' in prompt
    # existing types unchanged
    assert '"Organization"' in prompt and '"FAQPage"' in prompt and '"WebSite"' in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_toolkit_service.py -q`
Expected: new tests FAIL with ImportError; existing tests pass.

- [ ] **Step 3: Implement**

In `backend/app/prompts/toolkit.py`:

1. Below `LLMS_TXT_VERSION` add `LLMS_FULL_TXT_VERSION = "v1"`.
2. Change `SCHEMA_JSON_VERSION = "v4"` to:

```python
# v5: add Service (one per main service) + BreadcrumbList to the @graph.
SCHEMA_JSON_VERSION = "v5"
```

3. After `build_llms_txt` add:

```python
def build_llms_full_txt(client: Client) -> str:
    location_parts = [p for p in [client.city, client.state, client.country] if p]
    location = ", ".join(location_parts)

    return f"""Generate an llms-full.txt file for this business — the extended companion \
to llms.txt, giving AI assistants the full picture in one file.

Required format — use exactly these section headings in this order:

# {client.name}
> [One-sentence tagline: what the business does and who it serves, under 20 words]

## About
[3-5 sentences: mission, core offering, history if inferable, what makes this business \
distinctive from competitors]

## Services
[For EACH main service or product: a "### Service name" subheading followed by 2-3 \
sentences describing what it is, who it's for, and what to expect. Infer services from \
the industry and description. 3-8 services.]

## Target Audience
[Specific description of who the business serves — be concrete, not generic]

## Location
[City, state/region, country — for local AI discovery. Omit this entire section if no \
location was provided.]

## Key Pages
[Bullet list of the site's likely key URLs using the website domain: homepage, and one \
per main service using clean, plausible paths like {client.website}/services. Only use \
the domain provided — never invent other domains.]

## Policies
[2-4 short bullets covering how the business typically works with customers: how to get \
started, consultations or quotes, what a first visit or engagement looks like. Infer \
conservatively from the industry — write nothing that promises specific prices or terms.]

## Contact
[Website URL. Include contact email on a second line only if one was provided.]

## Key Facts
[5-8 bullet points an AI should know when deciding whether to recommend this business]

## Questions & Answers
[8-12 Q&A pairs. Write the questions exactly as a potential customer would ask an AI \
assistant — natural, conversational language. Each answer must be 1-3 sentences, \
specific to this business, and naturally include the business name. Cover: what the \
business does, who it's for, each main service, what makes it different, how to get \
started, and location/area served if provided.]

---

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or "Not provided"}
Target audience: {client.target_audience or "Not provided"}
Location: {location or "Not provided"}
Contact email: {client.contact_email or "Not provided"}

Rules:
- Start with # {client.name} on the very first line — no blank line before it
- Be specific to THIS business — no generic filler
- Never invent prices, phone numbers, addresses, or URLs on other domains
- Omit the Location section entirely if no location was provided
- Output ONLY the raw llms-full.txt content. No explanations. No code block wrappers."""
```

4. In `build_schema_json`, make exactly these edits:
   - Change the line `containing exactly these 4 schemas:` to `containing exactly these 6 schemas:`
   - After the `Schema 4 — FAQPage:` block (before the `---` separator), insert:

```python
Schema 5 — Services:
  One "Service" entry per main service of the business (2-5 services, inferred from the
  industry and description). For each:
  @type: "Service"
  @id: "{client.website}/#service-N"  (N = 1, 2, 3…)
  name: the service name
  description: one sentence
  provider: {{"@id": "{client.website}/#business"}}
  areaServed: "{location or 'omit if unknown'}"  (omit the field if no location was provided)

Schema 6 — BreadcrumbList:
  @type: "BreadcrumbList"
  @id: "{client.website}/#breadcrumbs"
  itemListElement: exactly 2 ListItem entries:
    position 1: name "Home", item "{client.website}"
    position 2: name "Services", item "{client.website}/services"
```

(These lines live inside the existing f-string — keep the doubled `{{ }}` braces exactly as shown.)

In `backend/app/services/toolkit_service.py`, add the import `build_llms_full_txt` to the existing `from app.prompts.toolkit import ...` line, then after `generate_llms_txt` add:

```python
def generate_llms_full_txt(client: Client) -> str:
    response = _anthropic_client().messages.create(
        model=_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": build_llms_full_txt(client)}],
    )
    record_llm_call(
        service="toolkit_llms_full_txt", model=_MODEL, response=response, client_id=client.id
    )
    return _strip_code_fences(response.content[0].text)
```

`generate_toolkit_files` is NOT changed — llms-full has its own generate endpoint (the UI shows a per-file Generate button when the column is null).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_toolkit_service.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/prompts/toolkit.py backend/app/services/toolkit_service.py backend/tests/test_toolkit_service.py
git commit -m "feat(toolkit): llms-full.txt generator + schema.json v5 (Service + BreadcrumbList)"
```

---

### Task 6: API routes + schemas

**Files:**
- Create: `backend/app/schemas/site_audit.py`
- Create: `backend/app/api/v1/site_audit.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/api/v1/toolkit.py`
- Modify: `backend/app/schemas/toolkit.py`
- Modify: `backend/app/schemas/ai_readiness.py`, `backend/app/services/ai_readiness_service.py` (competitor_id passthrough)
- Test: `backend/tests/test_api_site_audit.py` (new), `backend/tests/test_api_toolkit.py` (append)

**Interfaces:**
- Produces routes: `POST /api/v1/clients/{id}/site-audit`, `GET /api/v1/clients/{id}/site-audit/latest`, `POST /api/v1/clients/{id}/site-audit/competitor/{competitor_id}`, `POST /api/v1/clients/{id}/toolkit/generate-llms-full`. `SiteAIReadiness` gains `competitor_id: uuid.UUID | None` (frontend Task 8 depends on it). `ToolkitFilesResponse` gains `llms_full_txt: str | None`, `llms_full_verified: bool`; `VerificationResult` gains `llms_full_verified: bool`.
- Consumes: Task 4's `run_and_persist_site_audit` / `get_latest_with_delta`; Task 3's `run_site_audit` / `summarize`; Task 5's `generate_llms_full_txt`; Task 2's 4-key `verify_all`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_api_site_audit.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

_CHECKS = [
    {"id": "https", "label": "Secure connection (HTTPS)", "status": "pass",
     "detail": "The site is served over a secure connection.", "fix": ""},
]


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.archived_at = None
    return m


def _fake_audit(client_id):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.client_id = client_id
    a.checks = _CHECKS
    a.passed, a.warned, a.failed, a.unknown = 1, 0, 0, 0
    a.created_at = datetime(2026, 7, 22)
    return a


def test_run_audit_returns_persisted_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.run_and_persist_site_audit",
               return_value=_fake_audit(fake_client.id)) as mock_run:
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/site-audit")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["passed"] == 1
    assert resp.json()["checks"][0]["id"] == "https"
    mock_run.assert_called_once()


def test_run_audit_400_when_no_website():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_client.website = None
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/site-audit")
    app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_latest_returns_null_when_no_audits():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.get_latest_with_delta", return_value=None):
        resp = TestClient(app).get(f"/api/v1/clients/{fake_client.id}/site-audit/latest")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() is None


def test_latest_returns_audit_with_delta():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    app.dependency_overrides[get_db] = lambda: mock_db
    payload = {"audit": _fake_audit(fake_client.id), "fixed": ["h1"], "regressed": [], "has_previous": True}
    with patch("app.api.v1.site_audit.get_latest_with_delta", return_value=payload):
        resp = TestClient(app).get(f"/api/v1/clients/{fake_client.id}/site-audit/latest")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["fixed"] == ["h1"]
    assert body["has_previous"] is True
    assert body["audit"]["passed"] == 1


def test_competitor_audit_live_only_never_persists():
    app, get_db = _make_app()
    fake_client = _fake_client()
    competitor = MagicMock()
    competitor.id = uuid.uuid4()
    competitor.client_id = fake_client.id
    competitor.name = "Rival Dental"
    competitor.website = "https://rival.com"
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, competitor]
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.site_audit.run_site_audit", return_value=_CHECKS):
        resp = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/site-audit/competitor/{competitor.id}"
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Rival Dental"
    assert body["passed"] == 1
    assert "not saved" in body["note"].lower()
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_competitor_audit_404_when_wrong_client():
    app, get_db = _make_app()
    fake_client = _fake_client()
    competitor = MagicMock()
    competitor.id = uuid.uuid4()
    competitor.client_id = uuid.uuid4()  # belongs to someone else
    mock_db = MagicMock()
    mock_db.get.side_effect = [fake_client, competitor]
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(
        f"/api/v1/clients/{fake_client.id}/site-audit/competitor/{competitor.id}"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_run_audit_requires_auth():
    from app.main import app
    resp = TestClient(app).post(f"/api/v1/clients/{uuid.uuid4()}/site-audit")
    assert resp.status_code == 401
```

Append to `backend/tests/test_api_toolkit.py`:

```python
def test_generate_llms_full_updates_row():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    fake_tf.llms_full_txt = None
    fake_tf.llms_full_verified = False
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.generate_llms_full_txt", return_value="# Acme — full"):
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/generate-llms-full")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert fake_tf.llms_full_txt == "# Acme — full"
    assert fake_tf.llms_full_verified is False


def test_generate_llms_full_404_without_base_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/generate-llms-full")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_verify_persists_llms_full_flag_without_touching_scores():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": False,
            "schema_verified": False,
            "robots_verified": False,
            "llms_full_verified": True,
        }
        resp = TestClient(app).post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["llms_full_verified"] is True
    assert fake_tf.llms_full_verified is True
    # llms-full alone must NOT flip either score dimension
    assert fake_client.technical_foundations_verified is False
    assert fake_client.structured_data_verified is False
```

Also update `_fake_toolkit` in `test_api_toolkit.py` to set the two new attributes (`m.llms_full_txt = None`, `m.llms_full_verified = False`) so response serialization has them.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_api_site_audit.py tests/test_api_toolkit.py -q`
Expected: FAIL — 404s (routes don't exist) / ImportErrors.

- [ ] **Step 3: Implement**

`backend/app/schemas/site_audit.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class SiteAuditCheck(BaseModel):
    id: str
    label: str
    status: str  # "pass" | "warn" | "fail" | "unknown"
    detail: str
    fix: str


class SiteAuditResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    checks: list[SiteAuditCheck]
    passed: int
    warned: int
    failed: int
    unknown: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SiteAuditLatestResponse(BaseModel):
    audit: SiteAuditResponse
    fixed: list[str]
    regressed: list[str]
    has_previous: bool


class CompetitorSiteAuditResponse(BaseModel):
    competitor_id: uuid.UUID
    name: str
    website: str | None
    checks: list[SiteAuditCheck]
    passed: int
    warned: int
    failed: int
    unknown: int
    note: str
```

`backend/app/api/v1/site_audit.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.competitor import Competitor
from app.schemas.site_audit import (
    CompetitorSiteAuditResponse,
    SiteAuditLatestResponse,
    SiteAuditResponse,
)
from app.services.site_audit_service import (
    get_latest_with_delta,
    run_and_persist_site_audit,
    run_site_audit,
    summarize,
)

router = APIRouter(prefix="/clients/{client_id}/site-audit", tags=["site-audit"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.post("", response_model=SiteAuditResponse, dependencies=[Depends(require_api_key)])
def run_audit(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    if not client.website:
        raise HTTPException(status_code=400, detail="Client has no website on file")
    return run_and_persist_site_audit(client_id, client.website, db)


@router.get(
    "/latest",
    response_model=SiteAuditLatestResponse | None,
    dependencies=[Depends(require_api_key)],
)
def latest(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return get_latest_with_delta(client_id, db)


@router.post(
    "/competitor/{competitor_id}",
    response_model=CompetitorSiteAuditResponse,
    dependencies=[Depends(require_api_key)],
)
def competitor_audit(
    client_id: uuid.UUID, competitor_id: uuid.UUID, db: Session = Depends(get_db)
):
    """Live audit of a competitor site — same checks, never persisted.

    A competitor's readiness never feeds the client's score (spec §4).
    """
    _get_client_or_404(client_id, db)
    comp = db.get(Competitor, competitor_id)
    if not comp or comp.client_id != client_id:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if not comp.website:
        raise HTTPException(status_code=400, detail="Competitor has no website on file")
    checks = run_site_audit(comp.website)
    s = summarize(checks)
    return CompetitorSiteAuditResponse(
        competitor_id=comp.id,
        name=comp.name,
        website=comp.website,
        checks=checks,
        passed=s["passed"],
        warned=s["warned"],
        failed=s["failed"],
        unknown=s["unknown"],
        note="Live check — not saved. A competitor's results never affect this client's score.",
    )
```

`backend/app/api/v1/router.py` — add `site_audit` to the import list and `router.include_router(site_audit.router)` after the toolkit line.

`backend/app/schemas/toolkit.py` — in `ToolkitFilesResponse` add (after `robots_txt`):

```python
    llms_full_txt: str | None = None
```

and after `robots_verified`:

```python
    llms_full_verified: bool = False
```

In `VerificationResult` add after `robots_verified`:

```python
    llms_full_verified: bool
```

`backend/app/api/v1/toolkit.py`:
1. Add `generate_llms_full_txt` to the service imports.
2. After the `generate` route add:

```python
@router.post(
    "/generate-llms-full",
    response_model=ToolkitFilesResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_llms_full(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    tf = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if not tf:
        raise HTTPException(status_code=404, detail="Generate the toolkit files first")
    tf.llms_full_txt = generate_llms_full_txt(client)
    tf.llms_full_verified = False
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_generated",
        note="llms-full.txt generated.",
    ))
    db.commit()
    db.refresh(tf)
    return tf
```

3. In the `verify` route, after `tf.robots_verified = results["robots_verified"]` add:

```python
    # Informational only — llms-full never touches dimension scores (spec §6).
    tf.llms_full_verified = results["llms_full_verified"]
```

4. In the `verified_names` list add the tuple `("llms-full.txt", results["llms_full_verified"]),` after the robots tuple. The two `client.technical_foundations_verified` / `client.structured_data_verified` lines are **unchanged** — do not add llms_full to them.
5. In the final `VerificationResult(...)` add `llms_full_verified=results["llms_full_verified"],`.

`backend/app/schemas/ai_readiness.py` — in `SiteAIReadiness` add:

```python
import uuid
# ... inside the class, after website:
    competitor_id: uuid.UUID | None = None
```

`backend/app/services/ai_readiness_service.py` — thread the id through:

```python
def check_site_ai_readiness(
    name: str, website: str | None, competitor_id: uuid.UUID | None = None
) -> SiteAIReadiness:
    if not website:
        return SiteAIReadiness(
            name=name, website=website, checked=False, has_llms_txt=False,
            competitor_id=competitor_id,
        )
    return SiteAIReadiness(
        name=name,
        website=website,
        checked=True,
        has_llms_txt=verify_llms_txt(website),
        blocked_ai_bots=check_robots_ai_bot_access(website),
        schema_types=check_homepage_schema(website),
        competitor_id=competitor_id,
    )
```

and in `compute_competitor_ai_readiness`, build sites as triples and unpack:

```python
    sites: list[tuple[str, str | None, uuid.UUID | None]] = [
        (client.name, client.website, None)
    ] + [(c.name, c.website, c.id) for c in competitors]

    def _safe_check(site: tuple[str, str | None, uuid.UUID | None]) -> SiteAIReadiness:
        name, website, comp_id = site
        try:
            return check_site_ai_readiness(name, website, comp_id)
        except Exception:
            logger.warning("ai_readiness_check_failed", name=name)
            return SiteAIReadiness(
                name=name, website=website, checked=False, has_llms_txt=False,
                competitor_id=comp_id,
            )
```

- [ ] **Step 4: Run the whole backend suite**

Run: `poetry run pytest -q`
Expected: all pass (existing ai_readiness tests still pass — the new param defaults to None).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/site_audit.py backend/app/api/v1/site_audit.py backend/app/api/v1/router.py backend/app/api/v1/toolkit.py backend/app/schemas/toolkit.py backend/app/schemas/ai_readiness.py backend/app/services/ai_readiness_service.py backend/tests/test_api_site_audit.py backend/tests/test_api_toolkit.py
git commit -m "feat(site-audit): API routes (run/latest/competitor) + toolkit llms-full endpoint"
```

---

### Task 7: Frontend — toolkit page (audit card + 4th file)

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/clients/[id]/toolkit/actions.ts`
- Create: `frontend/src/components/SiteAuditResults.tsx`
- Create: `frontend/src/components/clients/SiteAuditCard.tsx`
- Modify: `frontend/src/app/clients/[id]/toolkit/page.tsx`
- Modify: `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx`

**Interfaces:**
- Produces: types `SiteAuditStatus`, `SiteAuditCheck`, `SiteAudit`, `SiteAuditLatest`, `CompetitorSiteAudit`; api fns `runSiteAudit`, `getLatestSiteAudit`, `runCompetitorSiteAudit`, `generateLlmsFullTxt`; shared component `SiteAuditResults({ checks })` (Task 8 reuses it).
- Consumes: Task 6's endpoints and response shapes.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, extend `ToolkitFiles` (after `robots_txt`): add `llms_full_txt: string | null` and (after `robots_verified`) `llms_full_verified: boolean`. Extend `VerificationResult` with `llms_full_verified: boolean`. In `SiteAIReadiness` add `competitor_id?: string | null`. Then append:

```ts
// ── Site AI-Readiness Audit ──────────────────────────────────────────────────

export type SiteAuditStatus = "pass" | "warn" | "fail" | "unknown"

export interface SiteAuditCheck {
  id: string
  label: string
  status: SiteAuditStatus
  detail: string
  fix: string
}

export interface SiteAudit {
  id: string
  client_id: string
  checks: SiteAuditCheck[]
  passed: number
  warned: number
  failed: number
  unknown: number
  created_at: string
}

export interface SiteAuditLatest {
  audit: SiteAudit
  fixed: string[]
  regressed: string[]
  has_previous: boolean
}

export interface CompetitorSiteAudit {
  competitor_id: string
  name: string
  website: string | null
  checks: SiteAuditCheck[]
  passed: number
  warned: number
  failed: number
  unknown: number
  note: string
}
```

- [ ] **Step 2: Add api.ts functions**

After the Toolkit block in `frontend/src/lib/api.ts`:

```ts
export function generateLlmsFullTxt(clientId: string): Promise<ToolkitFiles> {
  return apiFetch<ToolkitFiles>(`/api/v1/clients/${clientId}/toolkit/generate-llms-full`, {
    method: "POST",
  })
}

// ── Site AI-Readiness Audit ──────────────────────────────────────────────────

export function runSiteAudit(clientId: string): Promise<SiteAudit> {
  return apiFetch<SiteAudit>(`/api/v1/clients/${clientId}/site-audit`, { method: "POST" })
}

export function getLatestSiteAudit(clientId: string): Promise<SiteAuditLatest | null> {
  return apiFetch<SiteAuditLatest | null>(`/api/v1/clients/${clientId}/site-audit/latest`)
}

// Live outbound check of a competitor site — never persisted.
export function runCompetitorSiteAudit(
  clientId: string,
  competitorId: string,
): Promise<CompetitorSiteAudit> {
  return apiFetch<CompetitorSiteAudit>(
    `/api/v1/clients/${clientId}/site-audit/competitor/${competitorId}`,
    { method: "POST" },
  )
}
```

Add `SiteAudit, SiteAuditLatest, CompetitorSiteAudit` to the file's type imports from `@/types`.

- [ ] **Step 3: Add server actions**

Append to `frontend/src/app/clients/[id]/toolkit/actions.ts` (extend the existing import from `@/lib/api` with `generateLlmsFullTxt as apiGenerateLlmsFull, runSiteAudit as apiRunSiteAudit, getLatestSiteAudit as apiGetLatestSiteAudit`, and the type import with `SiteAuditLatest`):

```ts
export async function generateLlmsFullAction(clientId: string): Promise<ToolkitFiles> {
  const files = await apiGenerateLlmsFull(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return files
}

export async function runSiteAuditAction(clientId: string): Promise<SiteAuditLatest | null> {
  await apiRunSiteAudit(clientId)
  // Re-read latest so the response includes the fixed/regressed delta.
  const latest = await apiGetLatestSiteAudit(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return latest
}
```

- [ ] **Step 4: Create the shared results component**

`frontend/src/components/SiteAuditResults.tsx`:

```tsx
// Shared grouped-results view for the site AI-readiness audit.
// Used by the toolkit page card and the competitors page inline audit.
import { CheckCircle, XCircle, AlertTriangle, HelpCircle } from "lucide-react"
import type { SiteAuditCheck, SiteAuditStatus } from "@/types"

const GROUPS: { title: string; ids: string[] }[] = [
  {
    title: "AI crawl access",
    ids: ["robots_exists", "robots_ai_bots", "llms_txt", "llms_full_txt", "https"],
  },
  { title: "Sitemap", ids: ["sitemap_exists", "sitemap_urls", "sitemap_fresh"] },
  {
    title: "Homepage signals",
    ids: [
      "title", "meta_description", "canonical", "open_graph", "h1",
      "heading_order", "viewport", "internal_links", "response_time",
    ],
  },
  { title: "Structured data", ids: ["jsonld_present", "jsonld_types"] },
]

function StatusChip({ status }: { status: SiteAuditStatus }) {
  if (status === "pass")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-score-strong">
        <CheckCircle className="h-3.5 w-3.5" /> Pass
      </span>
    )
  if (status === "warn")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-score-watch">
        <AlertTriangle className="h-3.5 w-3.5" /> Improve
      </span>
    )
  if (status === "fail")
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-destructive">
        <XCircle className="h-3.5 w-3.5" /> Fix
      </span>
    )
  return (
    <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
      <HelpCircle className="h-3.5 w-3.5" /> Couldn&apos;t check
    </span>
  )
}

export function SiteAuditResults({ checks }: { checks: SiteAuditCheck[] }) {
  const byId = new Map(checks.map((c) => [c.id, c]))
  return (
    <div className="space-y-5">
      {GROUPS.map((group) => {
        const groupChecks = group.ids
          .map((id) => byId.get(id))
          .filter((c): c is SiteAuditCheck => c !== undefined)
        if (groupChecks.length === 0) return null
        return (
          <div key={group.title}>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              {group.title}
            </p>
            <div className="divide-y rounded-md border">
              {groupChecks.map((check) => (
                <div key={check.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">{check.label}</span>
                    <StatusChip status={check.status} />
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{check.detail}</p>
                  {check.fix && (
                    <p className="mt-1 text-xs text-foreground/80">
                      <span className="font-medium">How to fix:</span> {check.fix}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 5: Create the audit card**

`frontend/src/components/clients/SiteAuditCard.tsx`:

```tsx
"use client"

import { useState, useTransition } from "react"
import { Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SiteAuditResults } from "@/components/SiteAuditResults"
import { runSiteAuditAction } from "@/app/clients/[id]/toolkit/actions"
import type { SiteAuditLatest } from "@/types"

export function SiteAuditCard({
  clientId,
  initialLatest,
}: {
  clientId: string
  initialLatest: SiteAuditLatest | null
}) {
  const [latest, setLatest] = useState<SiteAuditLatest | null>(initialLatest)
  const [failed, setFailed] = useState(false)
  const [pending, startTransition] = useTransition()

  function handleRun() {
    setFailed(false)
    startTransition(async () => {
      try {
        setLatest(await runSiteAuditAction(clientId))
      } catch {
        setFailed(true)
      }
    })
  }

  const audit = latest?.audit ?? null

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-display text-lg font-semibold">Site AI-Readiness Audit</h3>
          <p className="text-sm text-muted-foreground mt-1">
            19 checks across AI crawl access, sitemap, homepage signals and structured
            data — each with a plain-English fix. Informational only, not part of the score.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRun} disabled={pending} className="shrink-0">
          {pending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          )}
          {pending ? "Auditing…" : audit ? "Run again" : "Run audit"}
        </Button>
      </div>

      {failed && (
        <p className="mt-3 text-sm text-destructive">Couldn&apos;t complete the audit — try again.</p>
      )}

      {audit && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>
              <span className="font-semibold text-score-strong">{audit.passed}</span> passed
              {" · "}
              <span className="font-semibold text-score-watch">{audit.warned}</span> to improve
              {" · "}
              <span className="font-semibold text-destructive">{audit.failed}</span> to fix
              {audit.unknown > 0 && (
                <>
                  {" · "}
                  {audit.unknown} couldn&apos;t check
                </>
              )}
            </span>
            <span>
              Last run{" "}
              {new Date(audit.created_at).toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
            {latest?.has_previous && (
              <span>
                Since last audit: {latest.fixed.length} fixed
                {latest.regressed.length > 0 && ` · ${latest.regressed.length} got worse`}
              </span>
            )}
          </div>
          <div className="mt-4">
            <SiteAuditResults checks={audit.checks} />
          </div>
        </>
      )}

      {!audit && !pending && (
        <p className="mt-4 text-sm text-muted-foreground">
          No audit yet — run one to see how ready this site is for AI search.
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Wire the toolkit page**

Replace `frontend/src/app/clients/[id]/toolkit/page.tsx` with:

```tsx
import { getToolkitFiles, getClient, getLatestSiteAudit } from "@/lib/api"
import { ToolkitClient } from "./ToolkitClient"
import { SiteAuditCard } from "@/components/clients/SiteAuditCard"
import type { SiteAuditLatest } from "@/types"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ToolkitPage({ params }: Props) {
  const { id } = await params
  let files = null
  let clientWebsite = ""
  let latestAudit: SiteAuditLatest | null = null
  try {
    const [fetchedFiles, client, fetchedAudit] = await Promise.all([
      getToolkitFiles(id),
      getClient(id),
      getLatestSiteAudit(id).catch(() => null),
    ])
    files = fetchedFiles
    clientWebsite = client.website
    latestAudit = fetchedAudit
  } catch {
    // Backend down or client not found — show empty state
  }
  return (
    <div className="space-y-8">
      <ToolkitClient clientId={id} initialFiles={files} clientWebsite={clientWebsite} />
      <SiteAuditCard clientId={id} initialLatest={latestAudit} />
    </div>
  )
}
```

- [ ] **Step 7: Add the 4th file to ToolkitClient**

In `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx` make these exact edits:

1. Import the new action and add a transition (top of component):

```tsx
import { generateToolkitAction, verifyToolkitAction, generateLlmsFullAction } from "./actions"
```

2. In `FILE_META`, after the `llms_txt` entry add:

```tsx
  llms_full_txt: {
    label: "llms-full.txt",
    filename: "llms-full.txt",
    instruction:
      "Upload this file to your website root next to llms.txt, so it's accessible at yourdomain.com/llms-full.txt. It's the extended version — optional, but it gives AI assistants a much richer picture of the business. It does not change the score.",
    expectedUrl: "/llms-full.txt",
  },
```

3. Change `FILE_KEYS` to:

```tsx
const FILE_KEYS: FileKey[] = ["llms_txt", "llms_full_txt", "schema_json", "robots_txt"]
```

4. Add a generate handler next to `handleGenerate` (uses its own transition):

```tsx
  const [isGeneratingFull, startFullTransition] = useTransition()

  function handleGenerateLlmsFull() {
    startFullTransition(async () => {
      setError(null)
      try {
        const result = await generateLlmsFullAction(clientId)
        setFiles(result)
      } catch {
        setError("Failed to generate llms-full.txt. Please try again.")
      }
    })
  }
```

5. Extend `isVerified`:

```tsx
  function isVerified(key: FileKey): boolean {
    if (!files) return false
    if (key === "llms_txt") return files.llms_verified
    if (key === "llms_full_txt") return files.llms_full_verified
    if (key === "schema_json") return files.schema_verified
    return files.robots_verified
  }
```

6. In `handleVerify`'s `setFiles({...})` call, add `llms_full_verified: result.llms_full_verified,` alongside the other three flags.

7. Guard null content: in the tab-content map, at the top of the non-null branch insert an early special case — when `key === "llms_full_txt" && !files.llms_full_txt`, render a generate box instead of the textarea/instructions:

```tsx
          {FILE_KEYS.map((key) =>
            activeTab !== key ? null : key === "llms_full_txt" && !files.llms_full_txt ? (
              <div key={key} className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
                <p className="font-medium">llms-full.txt not generated yet</p>
                <p className="text-sm mt-1 max-w-md mx-auto">
                  The extended companion to llms.txt — services in detail, more Q&amp;As,
                  policies and key pages. Optional, and doesn&apos;t change the score.
                </p>
                <Button className="mt-4" onClick={handleGenerateLlmsFull} disabled={isGeneratingFull}>
                  {isGeneratingFull && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Generate llms-full.txt
                </Button>
              </div>
            ) : (
              /* existing tab content block unchanged, but change the textarea
                 value to {files[key] ?? ""} and the copy/download handlers are
                 only reachable when content exists */
```

Also change `handleCopy`/`handleDownload` to use `files![key] ?? ""`.

8. Type note: `files[key]` is now `string | null` for the union — the `?? ""` coercions above keep TypeScript happy.

- [ ] **Step 8: Typecheck + build**

Run from `frontend/`:

```bash
npx tsc --noEmit
```
Expected: no errors.

```bash
npm run build
```
Expected: build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts "frontend/src/app/clients/[id]/toolkit/actions.ts" frontend/src/components/SiteAuditResults.tsx frontend/src/components/clients/SiteAuditCard.tsx "frontend/src/app/clients/[id]/toolkit/page.tsx" "frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx"
git commit -m "feat(site-audit): toolkit page audit card + llms-full.txt file card"
```

---

### Task 8: Frontend — competitor "Full audit" button

**Files:**
- Modify: `frontend/src/app/clients/[id]/competitors/actions.ts`
- Modify: `frontend/src/components/competitors/AIReadinessSection.tsx`

**Interfaces:**
- Consumes: `runCompetitorSiteAudit` (api.ts, Task 7), `SiteAuditResults` component (Task 7), `SiteAIReadiness.competitor_id` (Task 6), `CompetitorSiteAudit` type (Task 7).

- [ ] **Step 1: Add the server action**

In `frontend/src/app/clients/[id]/competitors/actions.ts`, extend the api import with `runCompetitorSiteAudit` and the type import with `CompetitorSiteAudit`, then append:

```ts
export async function runCompetitorSiteAuditAction(
  clientId: string,
  competitorId: string,
): Promise<CompetitorSiteAudit> {
  return runCompetitorSiteAudit(clientId, competitorId)
}
```

- [ ] **Step 2: Add the button + inline results**

In `frontend/src/components/competitors/AIReadinessSection.tsx`:

1. Extend imports:

```tsx
import type { CompetitorAIReadiness, SiteAIReadiness, CompetitorSiteAudit } from "@/types"
import { checkAIReadinessAction, runCompetitorSiteAuditAction } from "@/app/clients/[id]/competitors/actions"
import { SiteAuditResults } from "@/components/SiteAuditResults"
```

2. Pass `clientId` into rows: change the two `<AIReadinessRow …/>` call sites to include `clientId={clientId}`.

3. Replace `AIReadinessRow`'s signature and add the audit state (full replacement of the component function):

```tsx
function AIReadinessRow({
  site,
  isYou = false,
  clientId,
}: {
  site: SiteAIReadiness
  isYou?: boolean
  clientId: string
}) {
  const [audit, setAudit] = useState<CompetitorSiteAudit | null>(null)
  const [auditFailed, setAuditFailed] = useState(false)
  const [auditPending, startAuditTransition] = useTransition()

  function handleFullAudit() {
    setAuditFailed(false)
    startAuditTransition(async () => {
      try {
        setAudit(await runCompetitorSiteAuditAction(clientId, site.competitor_id!))
      } catch {
        setAuditFailed(true)
      }
    })
  }

  if (!site.checked) {
    return (
      <div className="flex items-center justify-between py-3 text-sm">
        <span className="font-medium">
          {site.name}
          {isYou && <span className="text-muted-foreground"> (you)</span>}
        </span>
        <span className="text-xs text-muted-foreground">No website on file</span>
      </div>
    )
  }

  return (
    <div className="py-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          {site.name}
          {isYou && <span className="text-muted-foreground"> (you)</span>}
        </span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">{site.website}</span>
          {site.competitor_id && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={handleFullAudit}
              disabled={auditPending}
            >
              {auditPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              {auditPending ? "Auditing…" : audit ? "Re-run full audit" : "Full audit"}
            </Button>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <span className="flex items-center gap-1.5 rounded-full border px-2.5 py-1">
          {site.has_llms_txt ? (
            <CheckCircle className="h-3.5 w-3.5 text-score-strong" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-muted-foreground/50" />
          )}
          llms.txt {site.has_llms_txt ? "found" : "missing"}
        </span>
        <span className="flex items-center gap-1.5 rounded-full border px-2.5 py-1">
          {site.schema_types.length > 0 ? (
            <CheckCircle className="h-3.5 w-3.5 text-score-strong" />
          ) : (
            <XCircle className="h-3.5 w-3.5 text-muted-foreground/50" />
          )}
          {site.schema_types.length > 0
            ? `Schema: ${site.schema_types.join(", ")}`
            : "No schema markup"}
        </span>
        {site.blocked_ai_bots.length > 0 && (
          <span className="flex items-center gap-1.5 rounded-full border border-score-watch/30 bg-score-watch-bg px-2.5 py-1 text-score-watch">
            <ShieldAlert className="h-3.5 w-3.5" />
            Blocks: {site.blocked_ai_bots.join(", ")}
          </span>
        )}
      </div>
      {auditFailed && (
        <p className="mt-2 text-xs text-destructive">Couldn&apos;t complete the audit — try again.</p>
      )}
      {audit && (
        <div className="mt-3 rounded-md border bg-muted/10 p-4">
          <p className="mb-3 text-xs text-muted-foreground">{audit.note}</p>
          <SiteAuditResults checks={audit.checks} />
        </div>
      )}
    </div>
  )
}
```

(The client's own row has `competitor_id == null`, so it never shows the button — the client's full audit lives on the toolkit page where it's persisted.)

- [ ] **Step 3: Typecheck + build**

Run from `frontend/`:

```bash
npx tsc --noEmit
```
Expected: no errors.

```bash
npm run build
```
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/app/clients/[id]/competitors/actions.ts" frontend/src/components/competitors/AIReadinessSection.tsx
git commit -m "feat(site-audit): per-competitor Full audit button on competitors page"
```

---

### Task 9: Verification gate + live walkthrough

**Files:** none (verification only)

- [ ] **Step 1: Run the seenby-verify skill** (definition-of-done gate: full pytest, frontend typecheck+build, banned-language grep, single alembic head). Fix anything it flags before proceeding.

- [ ] **Step 2: Banned-language spot check on the new client-facing strings**

```bash
grep -rniE "cited|uncited|mentioned|citation" backend/app/services/site_audit_service.py backend/app/prompts/toolkit.py frontend/src/components/SiteAuditResults.tsx frontend/src/components/clients/SiteAuditCard.tsx
```
Expected: no matches (CLAUDE.md §2).

- [ ] **Step 3: Live walkthrough** (seenby-demo-check habits — use the `run-app` skill to start both servers):
  1. Open `/clients/[id]/toolkit` for a demo client → "Site AI-Readiness Audit" card renders below the generators.
  2. Click **Run audit** → grouped A–D results appear with pass/warn/fail chips, detail + fix text, "last run" date. Verify the ActivityLog page shows the `site_audit_run` entry.
  3. Run it a second time → "Since last audit: N fixed" delta line appears.
  4. On the toolkit file tabs: llms-full.txt tab shows the Generate box; generate it (real Claude call), then copy/download/instructions render like the other three; **Verify live** now reports 4 files and the Score impact panel numbers are unchanged by llms-full.
  5. Open `/clients/[id]/competitors` → "Full audit" button on each competitor row runs the live audit inline with the "not saved" note; confirm no new `site_audits` row was created for it.
  6. Confirm the public share view (`/view/[token]`) shows nothing new (this phase is admin-only).

- [ ] **Step 4: Final commit if the walkthrough forced any fixes, then report**

Report must state: what was verified with command output, what was only walked through visually, and that the **prod Supabase migration has NOT been run** (it happens via seenby-release at deploy time).

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** §3 all 19 checks → Task 3; §4 model/persistence/live-only competitors → Tasks 1, 4, 6; §5 three routes → Task 6; §6 llms-full generator, schema v5, model columns, verify 4th key with no score impact → Tasks 1, 5, 6; §7 toolkit card, 4th file card, competitor button, shared component → Tasks 7, 8; §8 language rules → literal fix strings + Task 9 grep; §9 error handling → `unknown` semantics in Task 3 (incl. homepage-poisons-C/D test); §10 all 6 listed test scenarios → Tasks 3 (1–5), 4 (6), plus toolkit/API tests; §11 build order preserved.
- **Deliberate judgment calls** (spec was silent): missing canonical → warn / cross-domain → fail; missing viewport → fail; og tags missing → warn; http-not-redirecting → warn while https-serving; competitor-with-no-website → 400 (button hidden client-side); `jsonld_types` accepts industry subtypes (Dentist etc.) as business types so our own generated schema passes.
- **Type consistency:** check dict shape `{id,label,status,detail,fix}` used identically in service, schemas, tests, and TS types; `verify_all` 4-key dict consumed by toolkit route + tests; `SiteAuditLatest{audit,fixed,regressed,has_previous}` identical in schema, service return, and TS.
