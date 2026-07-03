# Citation Provenance + Share-of-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the source citations Perplexity returns during a scan, determine which brands appear on each cited third-party page, and surface a Share-of-Source breakdown plus a ranked "acquisition list" on the admin competitors page.

**Architecture:** Perplexity citations are captured inline during the scan into a new `scan_query_sources` table (fast, no network beyond the query). A best-effort post-commit step (`enrich_scan_sources`) then classifies each source domain and fetches third-party pages through the existing SSRF-guarded crawler, running deterministic brand-string matching to record who appears on each page. A read-model service aggregates this into Share-of-Source, an acquisition list, and flip targets, exposed via one admin endpoint and rendered as a new section on the existing competitors page.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest (SQLite in-memory), Next.js 15 (React server components), shadcn/ui, TypeScript.

## Global Constraints

- **Real citations only** — no LLM-inferred source attribution anywhere. Presence is determined solely by `detect_brand_mention` (deterministic string match).
- **Perplexity-only** — sources are captured only from the `perplexity` platform. Other platform clients are unchanged.
- **Client-query rows only** — sources come only from `ScanQueryResult` rows where `competitor_id IS NULL`.
- **Purge-proof** — `scan_query_sources` stores URLs/domains/flags, never raw response text; it survives the 90-day raw-response purge.
- **Never sink a scan** — enrichment is best-effort: on any failure, `db.rollback()` and swallow; the scan stays `completed`. Mirrors the existing alert/action-center post-commit steps in `run_scan`.
- **Reuse the SSRF guard** — all outbound fetches go through `app.services.url_safety.safe_get` / `is_safe_crawl_url`. Never call `httpx` directly against a cited URL.
- **Admin-only in v1** — no client view (`/view/[token]/*`) and no PDF changes.
- **Backend conventions (CLAUDE.md §10):** routes in `app/api/v1/`, logic in `app/services/`, one Alembic migration per schema change (no raw `ALTER TABLE`).
- **Frontend conventions (CLAUDE.md §10):** API calls only through `src/lib/api.ts`; types in `src/types/index.ts`; shadcn/ui only.
- **Language rules (CLAUDE.md §2):** admin copy may use "sources"; never use "cited"/"citation rate"/"ranking" in any client-safe string.
- **Test commands run from `backend/`** using `python -m pytest`.

---

## File Structure

**Backend — create:**
- `backend/app/models/scan_query_source.py` — the `ScanQuerySource` ORM model.
- `backend/app/services/provenance_service.py` — domain helpers, `enrich_scan_sources`, `compute_share_of_source`.
- `backend/app/schemas/provenance.py` — `ShareOfSourceResponse` and children.
- `backend/alembic/versions/<rev>_create_scan_query_sources_table.py` — migration.
- `backend/tests/test_perplexity_citations.py`, `test_provenance_capture.py`, `test_provenance_enrichment.py`, `test_provenance_share.py`, `test_api_provenance.py`.

**Backend — modify:**
- `backend/app/services/platform_clients/base.py` — add `SourceCitation`, `PlatformResult.citations`.
- `backend/app/services/platform_clients/perplexity.py` — parse `search_results`/`citations`.
- `backend/app/models/scan_query_result.py` — add `sources` relationship.
- `backend/app/services/scan_service.py` — inline source capture + post-commit `enrich_scan_sources` call.
- `backend/app/api/v1/competitors.py` — add `GET /provenance`.
- `backend/tests/conftest.py` — import the new model so `create_all` builds its table.

**Frontend — create:**
- `frontend/src/components/competitors/ShareOfSourceSection.tsx` — the UI section.

**Frontend — modify:**
- `frontend/src/types/index.ts` — Share-of-Source types.
- `frontend/src/lib/api.ts` — `getProvenance`.
- `frontend/src/app/clients/[id]/competitors/page.tsx` — fetch + render the section.

---

## Task 1: Capture citations in `PlatformResult` + Perplexity client

**Files:**
- Modify: `backend/app/services/platform_clients/base.py`
- Modify: `backend/app/services/platform_clients/perplexity.py`
- Test: `backend/tests/test_perplexity_citations.py`

**Interfaces:**
- Produces: `SourceCitation(url: str, title: str | None, rank: int)` (frozen dataclass) and `PlatformResult.citations: tuple[SourceCitation, ...]` (defaults to `()`), both in `base.py`. `PerplexityClient.query` returns citations parsed from the payload.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_perplexity_citations.py`:

```python
from unittest.mock import MagicMock, patch

from app.services.platform_clients import perplexity
from app.services.platform_clients.base import SourceCitation


def _payload(extra: dict) -> dict:
    base = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    base.update(extra)
    return base


def _patch_post(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return patch.object(perplexity.httpx, "post", return_value=resp)


def test_parses_search_results_shape():
    payload = _payload({"search_results": [
        {"title": "Best CRMs", "url": "https://a.com/x", "date": "2026-01-01"},
        {"title": None, "url": "https://b.com/y"},
    ]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert result.citations == (
        SourceCitation(url="https://a.com/x", title="Best CRMs", rank=1),
        SourceCitation(url="https://b.com/y", title=None, rank=2),
    )


def test_falls_back_to_legacy_citations_list():
    payload = _payload({"citations": ["https://a.com/x", "https://b.com/y"]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert [c.url for c in result.citations] == ["https://a.com/x", "https://b.com/y"]
    assert result.citations[0].rank == 1


def test_no_sources_yields_empty_tuple():
    with _patch_post(_payload({})):
        result = perplexity.PerplexityClient("key").query("q")
    assert result.citations == ()


def test_skips_entries_without_url():
    payload = _payload({"search_results": [{"title": "x"}, {"url": "https://b.com/y"}]})
    with _patch_post(payload):
        result = perplexity.PerplexityClient("key").query("q")
    assert [c.url for c in result.citations] == ["https://b.com/y"]
    assert result.citations[0].rank == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_perplexity_citations.py -v`
Expected: FAIL — `ImportError: cannot import name 'SourceCitation'`.

- [ ] **Step 3: Add `SourceCitation` and `citations` to `base.py`**

In `backend/app/services/platform_clients/base.py`, add after the imports and before `PlatformResult`:

```python
@dataclass(frozen=True)
class SourceCitation:
    """A single source the platform reported using to answer a query."""

    url: str
    title: str | None
    rank: int  # 1-based position in the platform's source list
```

Then add the field to `PlatformResult` (keep existing fields; add last so it stays optional):

```python
@dataclass(frozen=True)
class PlatformResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    citations: tuple[SourceCitation, ...] = ()
```

- [ ] **Step 4: Parse citations in `perplexity.py`**

In `backend/app/services/platform_clients/perplexity.py`, import `SourceCitation`:

```python
from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformNotConfiguredError,
    PlatformResult,
    SourceCitation,
    query_with_retry,
)
```

Add a module-level parser:

```python
def _parse_citations(payload: dict) -> tuple[SourceCitation, ...]:
    """Extract sources from a Perplexity response.

    Prefers the newer `search_results` (list of {title, url, date}); falls back
    to the legacy `citations` (list of URL strings). Entries without a URL are
    dropped; rank is the 1-based position among kept entries.
    """
    results = payload.get("search_results")
    if isinstance(results, list) and results:
        parsed = []
        for item in results:
            if isinstance(item, dict) and item.get("url"):
                parsed.append((item["url"], item.get("title")))
        if parsed:
            return tuple(
                SourceCitation(url=url, title=title, rank=i)
                for i, (url, title) in enumerate(parsed, start=1)
            )
    citations = payload.get("citations")
    if isinstance(citations, list) and citations:
        urls = [c for c in citations if isinstance(c, str) and c]
        return tuple(
            SourceCitation(url=url, title=None, rank=i)
            for i, url in enumerate(urls, start=1)
        )
    return ()
```

In `_call`, add `citations=_parse_citations(payload)` to the returned `PlatformResult(...)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_perplexity_citations.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/platform_clients/base.py backend/app/services/platform_clients/perplexity.py backend/tests/test_perplexity_citations.py
git commit -m "feat(provenance): capture Perplexity source citations in PlatformResult"
```

---

## Task 2: `ScanQuerySource` model + migration

**Files:**
- Create: `backend/app/models/scan_query_source.py`
- Modify: `backend/app/models/scan_query_result.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/alembic/versions/<rev>_create_scan_query_sources_table.py`
- Test: `backend/tests/test_provenance_capture.py` (model-creation portion)

**Interfaces:**
- Produces: `ScanQuerySource` with columns `id`, `scan_query_result_id`, `url`, `domain`, `title`, `rank`, `source_type`, `fetch_status`, `present_brands`, `created_at`; and `ScanQueryResult.sources` relationship (cascade insert/delete).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_provenance_capture.py`:

```python
import uuid

from app.models.scan import Scan
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com")
    db.add(c)
    db.commit()
    return c


def test_sources_cascade_insert_via_relationship(db):
    c = _client(db)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="completed")
    db.add(scan)
    db.commit()

    sqr = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best crm", response_text="…", brand_detected=False,
    )
    sqr.sources.append(
        ScanQuerySource(url="https://x.com/a", domain="x.com", title="A", rank=1)
    )
    db.add(sqr)
    db.commit()

    rows = db.query(ScanQuerySource).all()
    assert len(rows) == 1
    assert rows[0].scan_query_result_id == sqr.id
    assert rows[0].fetch_status == "pending"
    assert rows[0].source_type is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.scan_query_source'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/scan_query_source.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ScanQuerySource(Base):
    """A source a platform cited when answering a client-owned query.

    Structured, purge-proof (no raw response text) — survives the 90-day raw
    purge like brand_detected. Captured inline during the scan; source_type /
    fetch_status / present_brands are filled by the post-commit enrichment step.
    """

    __tablename__ = "scan_query_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_query_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_query_results.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    # client_owned | competitor_owned | third_party ; null until enriched
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # pending | ok | blocked | error
    fetch_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    # {"client": bool, "competitors": [competitor_id_str, ...]} ; null until enriched
    present_brands: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    scan_query_result = relationship("ScanQueryResult", back_populates="sources")
```

- [ ] **Step 4: Add the relationship on `ScanQueryResult`**

In `backend/app/models/scan_query_result.py`, add the import and relationship. Update the import line:

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
```

Add at the end of the class body (after `created_at`):

```python
    sources: Mapped[list["ScanQuerySource"]] = relationship(
        "ScanQuerySource",
        back_populates="scan_query_result",
        cascade="all, delete-orphan",
    )
```

- [ ] **Step 5: Register the model in conftest**

In `backend/tests/conftest.py`, append `scan_query_source` to the models import line (line 9) so `Base.metadata.create_all` builds the table:

```python
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_capture.py -v`
Expected: PASS (1 passed).

- [ ] **Step 7: Generate the migration skeleton**

Run from `backend/`: `alembic revision -m "create scan_query_sources table"`
This stamps `down_revision` to the current head automatically. Note the generated filename.

- [ ] **Step 8: Fill in the migration**

Edit the generated file's `upgrade`/`downgrade` (keep the auto-filled `revision`/`down_revision` untouched):

```python
def upgrade() -> None:
    op.create_table(
        "scan_query_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scan_query_result_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("fetch_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("present_brands", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["scan_query_result_id"], ["scan_query_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_query_sources_domain", "scan_query_sources", ["domain"])
    op.create_index("ix_scan_query_sources_result_id", "scan_query_sources", ["scan_query_result_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_query_sources_result_id", table_name="scan_query_sources")
    op.drop_index("ix_scan_query_sources_domain", table_name="scan_query_sources")
    op.drop_table("scan_query_sources")
```

Add the postgresql import at the top with the other imports:

```python
from sqlalchemy.dialects import postgresql
```

- [ ] **Step 9: Verify the migration chain is linear**

Run from `backend/`: `alembic history | head -5` and confirm the new revision sits at the head with a single parent. If a dev database is available, run `alembic upgrade head` and expect no error.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/scan_query_source.py backend/app/models/scan_query_result.py backend/tests/conftest.py backend/tests/test_provenance_capture.py backend/alembic/versions/
git commit -m "feat(provenance): add scan_query_sources table and relationship"
```

---

## Task 3: Domain helpers (`normalize_domain`, `classify_source_type`)

**Files:**
- Create: `backend/app/services/provenance_service.py`
- Test: `backend/tests/test_provenance_share.py` (helpers portion)

**Interfaces:**
- Produces: `normalize_domain(url: str) -> str` (lowercased host, `www.` stripped, empty string on garbage). `classify_source_type(domain: str, client_domain: str, competitor_domains: dict[str, str]) -> str` returning `"client_owned"`, `"competitor_owned"`, or `"third_party"`. `competitor_domains` maps normalized domain → competitor id string.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_provenance_share.py`:

```python
from app.services import provenance_service as ps


def test_normalize_domain_strips_www_and_scheme():
    assert ps.normalize_domain("https://www.Acme.com/best-crm") == "acme.com"
    assert ps.normalize_domain("http://blog.acme.com/x") == "blog.acme.com"
    assert ps.normalize_domain("acme.com") == "acme.com"


def test_normalize_domain_handles_garbage():
    assert ps.normalize_domain("") == ""
    assert ps.normalize_domain("not a url") == ""


def test_classify_source_type():
    comp_domains = {"rival.com": "comp-1"}
    assert ps.classify_source_type("acme.com", "acme.com", comp_domains) == "client_owned"
    assert ps.classify_source_type("rival.com", "acme.com", comp_domains) == "competitor_owned"
    assert ps.classify_source_type("g2.com", "acme.com", comp_domains) == "third_party"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_share.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.provenance_service'`.

- [ ] **Step 3: Write the helpers**

Create `backend/app/services/provenance_service.py`:

```python
"""Citation provenance + Share-of-Source (Perplexity-only, v1).

Sources are captured inline during a scan (scan_service). This module owns:
- domain normalization + classification helpers,
- enrich_scan_sources: best-effort post-commit fetch + deterministic brand match,
- compute_share_of_source: the admin read model.
"""
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


def normalize_domain(url: str) -> str:
    """Lowercased host with a leading 'www.' stripped; '' when unparseable."""
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    # A cited source is always a real web host: reject anything with no dot or an
    # embedded space (urlparse keeps "not a url" as the host otherwise).
    if not host or " " in host or "." not in host:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_source_type(
    domain: str, client_domain: str, competitor_domains: dict[str, str]
) -> str:
    if domain and domain == client_domain:
        return "client_owned"
    if domain in competitor_domains:
        return "competitor_owned"
    return "third_party"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_share.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provenance_service.py backend/tests/test_provenance_share.py
git commit -m "feat(provenance): domain normalization and source classification helpers"
```

---

## Task 4: Inline source capture in the scan flow

**Files:**
- Modify: `backend/app/services/scan_service.py`
- Test: `backend/tests/test_provenance_capture.py` (add capture-flow test)

**Interfaces:**
- Consumes: `PlatformResult.citations` (Task 1), `ScanQuerySource` + `ScanQueryResult.sources` (Task 2), `normalize_domain` (Task 3).
- Produces: after `run_scan`, `scan_query_sources` rows exist for Perplexity client-query results, `fetch_status="pending"`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_provenance_capture.py`:

```python
from unittest.mock import patch

from app.services import scan_service
from app.services.platform_clients.base import PlatformResult, SourceCitation
from app.models.scan_query_source import ScanQuerySource


class _FakePerplexity:
    platform = "perplexity"

    def query(self, prompt):
        return PlatformResult(
            text="Acme is great", model="sonar", input_tokens=1, output_tokens=1,
            citations=(SourceCitation(url="https://g2.com/acme", title="G2", rank=1),),
        )


def test_capture_writes_pending_sources_for_perplexity_client_queries(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
               enabled_platforms=["perplexity"])
    db.add(c)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="pending")
    db.add(scan)
    db.commit()

    with patch.object(scan_service, "get_platform_client", return_value=_FakePerplexity()), \
         patch.object(scan_service, "record_llm_usage"), \
         patch.object(scan_service, "extract_position", return_value=None), \
         patch.object(scan_service, "sync_remediation_items"), \
         patch("app.services.provenance_service.enrich_scan_sources"):
        scan_service.run_scan(scan.id, db)

    sources = db.query(ScanQuerySource).all()
    assert sources, "expected captured sources"
    assert all(s.fetch_status == "pending" and s.source_type is None for s in sources)
    assert all(s.domain == "g2.com" for s in sources)
```

> Note: `_INTER_QUERY_DELAY_SECONDS` sleeps 0.5s per query. For a fast test, also patch it: add `patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0)` to the `with` block.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_capture.py::test_capture_writes_pending_sources_for_perplexity_client_queries -v`
Expected: FAIL — no `ScanQuerySource` rows (capture not implemented).

- [ ] **Step 3: Add capture in `_run_platform_queries`**

In `backend/app/services/scan_service.py`, add imports near the top:

```python
from app.models.scan_query_source import ScanQuerySource
from app.services.provenance_service import normalize_domain
```

In `_run_platform_queries`, in the **client-query loop only** (the `for q in build_client_queries(...)` loop), replace the `results.append(ScanQueryResult(...))` call with a captured variable plus source attachment:

```python
        sqr = ScanQueryResult(
            scan_id=scan.id,
            platform=platform,
            competitor_id=None,
            category=q["category"],
            query_text=q["query_text"],
            response_text=response_text,
            brand_detected=detected,
            recommendation_position=position,
        )
        if platform == "perplexity":
            for c in result.citations:
                sqr.sources.append(
                    ScanQuerySource(
                        url=c.url,
                        domain=normalize_domain(c.url),
                        title=c.title,
                        rank=c.rank,
                    )
                )
        results.append(sqr)
```

Leave the competitor-query loop unchanged (no sources for competitor rows).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_capture.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_service.py backend/tests/test_provenance_capture.py
git commit -m "feat(provenance): capture Perplexity sources inline during scan"
```

---

## Task 5: `enrich_scan_sources` — fetch + deterministic brand match

**Files:**
- Modify: `backend/app/services/provenance_service.py`
- Test: `backend/tests/test_provenance_enrichment.py`

**Interfaces:**
- Consumes: `ScanQuerySource` rows (`fetch_status="pending"`), `safe_get`/`is_safe_crawl_url`/`UnsafeUrlError` from `app.services.url_safety`, `detect_brand_mention`.
- Produces: `enrich_scan_sources(scan_id: uuid.UUID, db: Session) -> None`. Sets `source_type`, `fetch_status` (`ok`/`blocked`/`error`), and `present_brands` on every source row of the scan's client queries. Fetches each unique third-party URL at most once. Commits its own changes.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_provenance_enrichment.py`:

```python
import uuid
from unittest.mock import patch

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import provenance_service as ps
from app.services.url_safety import SafeResponse, UnsafeUrlError


def _setup(db, urls):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
                    enabled_platforms=["perplexity"])
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival", website="https://rival.com")
    db.add_all([client, comp])
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed")
    db.add(scan)
    sqr = ScanQueryResult(scan_id=scan.id, platform="perplexity", category="recommendation",
                          query_text="best crm", response_text="…", brand_detected=False)
    for i, u in enumerate(urls, start=1):
        sqr.sources.append(ScanQuerySource(url=u, domain=ps.normalize_domain(u), title=None, rank=i))
    db.add(sqr)
    db.commit()
    return client, comp, scan


def test_third_party_presence_from_page_text(db):
    _setup(db, ["https://g2.com/crm"])
    page = SafeResponse(status_code=200, text="<p>Rival is the top pick.</p>",
                        headers={"content-type": "text/html"})
    with patch.object(ps, "safe_get", return_value=page):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    row = db.query(ScanQuerySource).one()
    assert row.source_type == "third_party"
    assert row.fetch_status == "ok"
    assert row.present_brands["client"] is False
    assert row.present_brands["competitors"] == [str(_comp_id(db))]


def test_owned_domains_need_no_fetch(db):
    client, comp, _ = _setup(db, ["https://acme.com/pricing", "https://rival.com/home"])
    called = []
    with patch.object(ps, "safe_get", side_effect=lambda *a, **k: called.append(1)):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    assert called == []  # owned domains classified without fetching
    rows = {r.domain: r for r in db.query(ScanQuerySource).all()}
    assert rows["acme.com"].source_type == "client_owned"
    assert rows["acme.com"].present_brands == {"client": True, "competitors": []}
    assert rows["rival.com"].source_type == "competitor_owned"
    assert rows["rival.com"].present_brands == {"client": False, "competitors": [str(comp.id)]}


def test_blocked_url_fails_open(db):
    _setup(db, ["https://internal.evil/x"])
    with patch.object(ps, "safe_get", side_effect=UnsafeUrlError("nope")):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    row = db.query(ScanQuerySource).one()
    assert row.fetch_status == "blocked"
    assert row.present_brands is None


def test_duplicate_url_fetched_once(db):
    _setup(db, ["https://g2.com/crm", "https://g2.com/crm"])
    page = SafeResponse(status_code=200, text="Acme rocks", headers={"content-type": "text/html"})
    calls = []
    def _fake_get(url, **kw):
        calls.append(url)
        return page
    with patch.object(ps, "safe_get", side_effect=_fake_get):
        ps.enrich_scan_sources(_latest_scan_id(db), db)
    assert len(calls) == 1
    rows = db.query(ScanQuerySource).all()
    assert all(r.fetch_status == "ok" for r in rows)


def _latest_scan_id(db):
    return db.query(Scan).first().id


def _comp_id(db):
    return db.query(Competitor).first().id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_enrichment.py -v`
Expected: FAIL — `AttributeError: module 'app.services.provenance_service' has no attribute 'enrich_scan_sources'`.

- [ ] **Step 3: Implement `enrich_scan_sources`**

Append to `backend/app/services/provenance_service.py`. Add imports at the top:

```python
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services.brand_detection import detect_brand_mention
from app.services.url_safety import safe_get, UnsafeUrlError
```

Add the constants and function:

```python
_FETCH_TIMEOUT = 10.0
_MAX_THIRD_PARTY_FETCHES = 60  # hard cap on outbound fetches per scan
_FETCH_WORKERS = 8


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _fetch_page_text(url: str) -> tuple[str, str | None]:
    """Return (fetch_status, text). status is ok/blocked/error; text None unless ok."""
    try:
        resp = safe_get(url, timeout=_FETCH_TIMEOUT)
    except UnsafeUrlError:
        return "blocked", None
    except Exception:
        return "error", None
    ctype = resp.headers.get("content-type", "").lower()
    if resp.status_code != 200 or "html" not in ctype:
        return "error", None
    return "ok", _extract_text(resp.text)


def enrich_scan_sources(scan_id: uuid.UUID, db: Session) -> None:
    """Classify + brand-match every captured source for a scan's client queries.

    Best-effort and idempotent-ish: only rows still 'pending' are processed.
    Owned domains are classified without a fetch; third-party pages are fetched
    once each (deduped by URL) through the SSRF-guarded crawler and matched with
    detect_brand_mention. Blocked/errored fetches fail open (present_brands None).
    """
    rows = (
        db.query(ScanQuerySource)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQuerySource.fetch_status == "pending",
        )
        .all()
    )
    if not rows:
        return

    result = db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scan_id).first()
    client = db.get(Client, result.scan.client_id) if result else None
    if client is None:
        return
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()

    client_domain = normalize_domain(client.website or "")
    competitor_domains = {
        normalize_domain(c.website): str(c.id) for c in competitors if c.website
    }
    comp_by_id = {str(c.id): c for c in competitors}

    by_url: dict[str, list[ScanQuerySource]] = defaultdict(list)
    for row in rows:
        by_url[row.url].append(row)

    third_party_urls: list[str] = []
    for url, occurrences in by_url.items():
        domain = normalize_domain(url)
        stype = classify_source_type(domain, client_domain, competitor_domains)
        for row in occurrences:
            row.source_type = stype
        if stype == "client_owned":
            for row in occurrences:
                row.fetch_status = "ok"
                row.present_brands = {"client": True, "competitors": []}
        elif stype == "competitor_owned":
            comp_id = competitor_domains[domain]
            for row in occurrences:
                row.fetch_status = "ok"
                row.present_brands = {"client": False, "competitors": [comp_id]}
        else:
            third_party_urls.append(url)

    third_party_urls = third_party_urls[:_MAX_THIRD_PARTY_FETCHES]
    fetched: dict[str, tuple[str, str | None]] = {}
    if third_party_urls:
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            for url, outcome in zip(
                third_party_urls, pool.map(_fetch_page_text, third_party_urls)
            ):
                fetched[url] = outcome

    for url in third_party_urls:
        status, text = fetched.get(url, ("error", None))
        occurrences = by_url[url]
        if status != "ok" or text is None:
            for row in occurrences:
                row.fetch_status = status
            continue
        present = {
            "client": detect_brand_mention(text, client.name),
            "competitors": [
                cid for cid, c in comp_by_id.items() if detect_brand_mention(text, c.name)
            ],
        }
        for row in occurrences:
            row.fetch_status = "ok"
            row.present_brands = present

    db.commit()
    logger.info(
        "scan_sources_enriched",
        scan_id=str(scan_id),
        total=len(rows),
        third_party_fetched=len(third_party_urls),
    )
```

> Note on `result.scan.client_id`: `ScanQueryResult` has no `scan` relationship in the current model. Replace with an explicit lookup to avoid depending on one: `from app.models.scan import Scan` and `scan = db.get(Scan, scan_id); client = db.get(Client, scan.client_id) if scan else None`. Use this form.

- [ ] **Step 4: Apply the client-lookup fix**

Add `from app.models.scan import Scan` to the imports and replace the client-lookup lines with:

```python
    scan = db.get(Scan, scan_id)
    client = db.get(Client, scan.client_id) if scan else None
    if client is None:
        return
```

(Remove the `result = db.query(...)` line — it is no longer used.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_enrichment.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/provenance_service.py backend/tests/test_provenance_enrichment.py
git commit -m "feat(provenance): enrich scan sources via SSRF-guarded fetch + brand match"
```

---

## Task 6: Wire enrichment into `run_scan` (best-effort, post-commit)

**Files:**
- Modify: `backend/app/services/scan_service.py`
- Test: `backend/tests/test_provenance_enrichment.py` (add isolation test)

**Interfaces:**
- Consumes: `enrich_scan_sources` (Task 5).
- Produces: `run_scan` calls `enrich_scan_sources` after the scan commits, wrapped so any failure rolls back and is swallowed — scan stays `completed`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_provenance_enrichment.py`:

```python
from app.services import scan_service
from app.services.platform_clients.base import PlatformResult, SourceCitation


class _FakePerplexity:
    platform = "perplexity"

    def query(self, prompt):
        return PlatformResult(text="x", model="sonar", input_tokens=1, output_tokens=1,
                              citations=(SourceCitation(url="https://g2.com/a", title=None, rank=1),))


def test_enrichment_failure_leaves_scan_completed(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
               enabled_platforms=["perplexity"])
    db.add(c)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="pending")
    db.add(scan)
    db.commit()

    with patch.object(scan_service, "get_platform_client", return_value=_FakePerplexity()), \
         patch.object(scan_service, "record_llm_usage"), \
         patch.object(scan_service, "extract_position", return_value=None), \
         patch.object(scan_service, "sync_remediation_items"), \
         patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0), \
         patch("app.services.provenance_service.enrich_scan_sources",
               side_effect=RuntimeError("boom")):
        scan_service.run_scan(scan.id, db)

    db.refresh(scan)
    assert scan.status == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_enrichment.py::test_enrichment_failure_leaves_scan_completed -v`
Expected: FAIL — `RuntimeError: boom` propagates (no wrapping yet), or scan marked `failed`.

- [ ] **Step 3: Add the best-effort call in `run_scan`**

In `backend/app/services/scan_service.py`, after the remediation sync block (the `sync_remediation_items(client.id, db)` call near the end of the `try`), add:

```python
        # Citation provenance enrichment — fetch cited third-party pages and
        # brand-match them. Best-effort: on failure roll back and swallow so a
        # slow/blocked fetch never undoes a good scan (CLAUDE.md §10).
        try:
            from app.services.provenance_service import enrich_scan_sources
            enrich_scan_sources(scan.id, db)
        except Exception as exc:
            db.rollback()
            logger.error("scan_sources_enrichment_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_enrichment.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_service.py backend/tests/test_provenance_enrichment.py
git commit -m "feat(provenance): run source enrichment best-effort after scan commit"
```

---

## Task 7: `compute_share_of_source` + response schema

**Files:**
- Create: `backend/app/schemas/provenance.py`
- Modify: `backend/app/services/provenance_service.py`
- Test: `backend/tests/test_provenance_share.py` (add aggregation tests)

**Interfaces:**
- Consumes: enriched `ScanQuerySource` rows.
- Produces: `ShareOfSourceResponse` (schema) and `compute_share_of_source(client_id: uuid.UUID, db: Session) -> ShareOfSourceResponse`.

Schema shapes (`backend/app/schemas/provenance.py`):
- `SourcePresence`: `competitor_id: uuid.UUID`, `name: str`
- `AcquisitionSource`: `url: str`, `domain: str`, `title: str | None`, `citation_count: int`, `competitors_present: list[SourcePresence]`
- `BrandShare`: `competitor_id: uuid.UUID | None` (None = client), `name: str`, `sources_present: int`, `share_pct: float`
- `ShareOfSourceResponse`: `last_scan_at: str | None`, `total_third_party_sources: int`, `client_share: BrandShare | None`, `competitor_shares: list[BrandShare]`, `acquisition_list: list[AcquisitionSource]`, `flip_targets: list[AcquisitionSource]`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_provenance_share.py`:

```python
import uuid

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource


def _seed_enriched(db):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com")
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival", website="https://rival.com")
    db.add_all([client, comp])
    from datetime import datetime
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
    db.add(scan)
    sqr = ScanQueryResult(scan_id=scan.id, platform="perplexity", category="recommendation",
                          query_text="best crm", response_text="…", brand_detected=False)
    # g2: competitor present, client absent, cited twice
    for rank in (1, 2):
        sqr.sources.append(ScanQuerySource(
            url="https://g2.com/crm", domain="g2.com", title="G2 CRMs", rank=rank,
            source_type="third_party", fetch_status="ok",
            present_brands={"client": False, "competitors": [str(comp.id)]}))
    # capterra: client present, cited once
    sqr.sources.append(ScanQuerySource(
        url="https://capterra.com/x", domain="capterra.com", title="Capterra", rank=3,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": []}))
    db.add(sqr)
    db.commit()
    return client, comp


def test_share_of_source_and_acquisition(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    resp = ps.compute_share_of_source(client.id, db)

    assert resp.total_third_party_sources == 2  # unique URLs
    assert resp.client_share.sources_present == 1
    assert resp.client_share.share_pct == 50.0
    assert resp.competitor_shares[0].sources_present == 1
    assert resp.competitor_shares[0].share_pct == 50.0

    # acquisition: g2 only (client absent, competitor present), citation_count 2
    assert len(resp.acquisition_list) == 1
    top = resp.acquisition_list[0]
    assert top.domain == "g2.com"
    assert top.citation_count == 2
    assert top.competitors_present[0].name == "Rival"
    assert resp.flip_targets == resp.acquisition_list[:3]


def test_no_scan_returns_empty(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com")
    db.add(client)
    db.commit()
    resp = ps.compute_share_of_source(client.id, db)
    assert resp.last_scan_at is None
    assert resp.total_third_party_sources == 0
    assert resp.acquisition_list == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance_share.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'compute_share_of_source'`.

- [ ] **Step 3: Write the schema**

Create `backend/app/schemas/provenance.py`:

```python
import uuid

from pydantic import BaseModel


class SourcePresence(BaseModel):
    competitor_id: uuid.UUID
    name: str


class AcquisitionSource(BaseModel):
    url: str
    domain: str
    title: str | None
    citation_count: int
    competitors_present: list[SourcePresence]


class BrandShare(BaseModel):
    competitor_id: uuid.UUID | None  # None = the client
    name: str
    sources_present: int
    share_pct: float


class ShareOfSourceResponse(BaseModel):
    last_scan_at: str | None
    total_third_party_sources: int
    client_share: BrandShare | None
    competitor_shares: list[BrandShare]
    acquisition_list: list[AcquisitionSource]
    flip_targets: list[AcquisitionSource]
```

- [ ] **Step 4: Implement `compute_share_of_source`**

Append to `backend/app/services/provenance_service.py`. Add imports:

```python
from app.models.scan import Scan
from app.schemas.provenance import (
    AcquisitionSource,
    BrandShare,
    ShareOfSourceResponse,
    SourcePresence,
)
```

(`Scan` may already be imported from Task 5 — do not duplicate.)

```python
def _empty_share(last_scan_at: str | None) -> ShareOfSourceResponse:
    return ShareOfSourceResponse(
        last_scan_at=last_scan_at,
        total_third_party_sources=0,
        client_share=None,
        competitor_shares=[],
        acquisition_list=[],
        flip_targets=[],
    )


def compute_share_of_source(client_id: uuid.UUID, db: Session) -> ShareOfSourceResponse:
    """Admin read model: Share-of-Source + acquisition list from the latest scan.

    Denominator is the count of unique third-party source URLs (fetch_status ok)
    cited by the client's own queries. A URL cited N times counts once for share
    but its N citations drive acquisition-list ranking.
    """
    latest = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )
    if not latest:
        return _empty_share(None)
    last_scan_at = latest.completed_at.isoformat() + "Z" if latest.completed_at else None

    rows = (
        db.query(ScanQuerySource)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == latest.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQuerySource.source_type == "third_party",
            ScanQuerySource.fetch_status == "ok",
        )
        .all()
    )
    if not rows:
        return _empty_share(last_scan_at)

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()
    comp_names = {str(c.id): c.name for c in competitors}
    client = db.get(Client, client_id)

    # Collapse occurrences to unique URLs; presence is identical across a URL's rows.
    unique: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.url] = counts.get(row.url, 0) + 1
        if row.url not in unique:
            unique[row.url] = {
                "domain": row.domain,
                "title": row.title,
                "present": row.present_brands or {"client": False, "competitors": []},
            }
    denom = len(unique)

    client_present = sum(1 for u in unique.values() if u["present"].get("client"))
    comp_present_counts: dict[str, int] = {cid: 0 for cid in comp_names}
    for u in unique.values():
        for cid in u["present"].get("competitors", []):
            if cid in comp_present_counts:
                comp_present_counts[cid] += 1

    def pct(n: int) -> float:
        return round(n / denom * 100, 1) if denom else 0.0

    client_share = BrandShare(
        competitor_id=None,
        name=client.name if client else "You",
        sources_present=client_present,
        share_pct=pct(client_present),
    )
    competitor_shares = [
        BrandShare(
            competitor_id=uuid.UUID(cid),
            name=comp_names[cid],
            sources_present=n,
            share_pct=pct(n),
        )
        for cid, n in sorted(comp_present_counts.items(), key=lambda kv: -kv[1])
    ]

    acquisition = []
    for url, meta in unique.items():
        present = meta["present"]
        comp_ids = [cid for cid in present.get("competitors", []) if cid in comp_names]
        if not present.get("client") and comp_ids:
            acquisition.append(
                AcquisitionSource(
                    url=url,
                    domain=meta["domain"],
                    title=meta["title"],
                    citation_count=counts[url],
                    competitors_present=[
                        SourcePresence(competitor_id=uuid.UUID(cid), name=comp_names[cid])
                        for cid in comp_ids
                    ],
                )
            )
    acquisition.sort(key=lambda a: -a.citation_count)

    return ShareOfSourceResponse(
        last_scan_at=last_scan_at,
        total_third_party_sources=denom,
        client_share=client_share,
        competitor_shares=competitor_shares,
        acquisition_list=acquisition,
        flip_targets=acquisition[:3],
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance_share.py -v`
Expected: PASS (5 passed — 3 helper + 2 aggregation).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/provenance.py backend/app/services/provenance_service.py backend/tests/test_provenance_share.py
git commit -m "feat(provenance): compute Share-of-Source read model and schema"
```

---

## Task 8: Admin API endpoint

**Files:**
- Modify: `backend/app/api/v1/competitors.py`
- Test: `backend/tests/test_api_provenance.py`

**Interfaces:**
- Consumes: `compute_share_of_source`, `ShareOfSourceResponse`, existing `_get_client_or_404` + `require_api_key`.
- Produces: `GET /api/v1/clients/{client_id}/competitors/provenance`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_provenance.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.schemas.provenance import ShareOfSourceResponse


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id):
    m = MagicMock()
    m.id = client_id
    m.archived_at = None
    return m


def test_provenance_returns_payload(monkeypatch):
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    app.dependency_overrides[get_db] = lambda: mock_db

    payload = ShareOfSourceResponse(
        last_scan_at=None, total_third_party_sources=0, client_share=None,
        competitor_shares=[], acquisition_list=[], flip_targets=[],
    )
    import app.api.v1.competitors as comp_api
    monkeypatch.setattr(comp_api, "compute_share_of_source", lambda cid, db: payload)

    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/provenance")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["total_third_party_sources"] == 0


def test_provenance_client_not_found_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/provenance")
    app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_provenance.py -v`
Expected: FAIL — 404 for both (route not registered) or ImportError.

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/v1/competitors.py`, add imports:

```python
from app.schemas.provenance import ShareOfSourceResponse
from app.services.provenance_service import compute_share_of_source
```

Add the route (place it next to the other GET routes, e.g. after `get_trends`):

```python
@router.get(
    "/provenance",
    response_model=ShareOfSourceResponse,
    dependencies=[Depends(require_api_key)],
)
def get_provenance(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return compute_share_of_source(client_id, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_provenance.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full backend provenance suite**

Run: `python -m pytest tests/test_perplexity_citations.py tests/test_provenance_capture.py tests/test_provenance_enrichment.py tests/test_provenance_share.py tests/test_api_provenance.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/competitors.py backend/tests/test_api_provenance.py
git commit -m "feat(provenance): add admin Share-of-Source endpoint"
```

---

## Task 9: Frontend — types, API client, and competitors-page section

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/competitors/ShareOfSourceSection.tsx`
- Modify: `frontend/src/app/clients/[id]/competitors/page.tsx`

**Interfaces:**
- Consumes: `GET /clients/{id}/competitors/provenance` → `ShareOfSourceResponse`.
- Produces: `getProvenance(clientId)` in `api.ts`; `<ShareOfSourceSection data={...} />`.

- [ ] **Step 1: Add the types**

In `frontend/src/types/index.ts`, add (match the existing type style in that file):

```typescript
export interface SourcePresence {
  competitor_id: string
  name: string
}

export interface AcquisitionSource {
  url: string
  domain: string
  title: string | null
  citation_count: number
  competitors_present: SourcePresence[]
}

export interface BrandShare {
  competitor_id: string | null
  name: string
  sources_present: number
  share_pct: number
}

export interface ShareOfSource {
  last_scan_at: string | null
  total_third_party_sources: number
  client_share: BrandShare | null
  competitor_shares: BrandShare[]
  acquisition_list: AcquisitionSource[]
  flip_targets: AcquisitionSource[]
}
```

- [ ] **Step 2: Add the API function**

In `frontend/src/lib/api.ts`, follow the existing `getCompetitorIntelligence` pattern. Import the type and add:

```typescript
import type { ShareOfSource } from "@/types"

export async function getProvenance(clientId: string): Promise<ShareOfSource> {
  return apiFetch<ShareOfSource>(`/clients/${clientId}/competitors/provenance`)
}
```

> Match the exact helper the other functions use (e.g. `apiFetch`/`fetchApi`). Open `api.ts`, copy the signature style of `getCompetitorTrends`, and mirror it.

- [ ] **Step 3: Create the section component**

Create `frontend/src/components/competitors/ShareOfSourceSection.tsx`:

```tsx
import { ExternalLink } from "lucide-react"
import type { ShareOfSource } from "@/types"

export function ShareOfSourceSection({ data }: { data: ShareOfSource }) {
  if (data.total_third_party_sources === 0) {
    return (
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-display text-lg font-semibold">Sources AI trusts in your category</h3>
        <p className="text-sm text-muted-foreground mt-1">
          No source data yet. Run a scan — SeenBy captures the sources AI leans on to
          answer your category&apos;s questions.
        </p>
      </div>
    )
  }

  const rows: { label: string; pct: number; you: boolean }[] = [
    ...(data.client_share
      ? [{ label: data.client_share.name, pct: data.client_share.share_pct, you: true }]
      : []),
    ...data.competitor_shares.map((c) => ({ label: c.name, pct: c.share_pct, you: false })),
  ]

  return (
    <div className="space-y-6">
      <div className="rounded-lg border bg-card p-5">
        <h3 className="font-display text-lg font-semibold">Sources AI trusts in your category</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Of the {data.total_third_party_sources} sources AI leaned on to answer your
          category&apos;s questions, here is who shows up on them.
        </p>
        <div className="mt-4 space-y-3">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-32 shrink-0 truncate text-sm font-medium">
                {r.label}
                {r.you && <span className="text-muted-foreground"> (you)</span>}
              </span>
              <div className="h-2.5 flex-1 rounded-full bg-muted">
                <div
                  className={`h-2.5 rounded-full ${r.you ? "bg-primary" : "bg-score-watch"}`}
                  style={{ width: `${Math.min(r.pct, 100)}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right text-sm tabular-nums">
                {r.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {data.acquisition_list.length > 0 && (
        <div className="rounded-lg border bg-card p-5">
          <h3 className="font-display text-lg font-semibold">
            Where your competitors are winning attention
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            Sources AI trusts where a competitor appears and you don&apos;t — ranked by how
            often AI cites them. Earning a mention here is the fastest way to flip the answer.
          </p>
          <div className="mt-4 divide-y">
            {data.acquisition_list.map((s) => (
              <div key={s.url} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm font-medium hover:underline"
                  >
                    <span className="truncate">{s.title ?? s.domain}</span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </a>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.domain} · on it: {s.competitors_present.map((c) => c.name).join(", ")}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  cited {s.citation_count}×
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Render the section on the competitors page**

In `frontend/src/app/clients/[id]/competitors/page.tsx`:

Add imports:

```tsx
import { getProvenance } from "@/lib/api"
import { ShareOfSourceSection } from "@/components/competitors/ShareOfSourceSection"
```

Add `getProvenance(id)` to the `Promise.all` and destructure it:

```tsx
  const [data, winLoss, trends, provenance] = await Promise.all([
    getCompetitorIntelligence(id).catch(() => null),
    getWinLoss(id).catch(() => null),
    getCompetitorTrends(id).catch(() => null),
    getProvenance(id).catch(() => null),
  ])
```

In the full-data view (after the `{/* Win/loss by query */}` block, before the competitor cards), render:

```tsx
      {/* Share of Source */}
      {provenance && <ShareOfSourceSection data={provenance} />}
```

- [ ] **Step 5: Type-check the frontend**

Run from `frontend/`: `npx tsc --noEmit`
Expected: no errors in the touched files. (If `apiFetch` name differs, fix the import in Step 2 to match `api.ts`.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/components/competitors/ShareOfSourceSection.tsx "frontend/src/app/clients/[id]/competitors/page.tsx"
git commit -m "feat(provenance): Share-of-Source section on admin competitors page"
```

---

## Self-Review — spec coverage

- Spec §4 (capture plumbing) → Task 1.
- Spec §5 (storage) → Task 2.
- Spec §6a (inline capture) → Task 4; §6b (enrichment) → Tasks 5–6.
- Spec §7 (read model) → Task 7.
- Spec §8 (API + admin UI) → Tasks 8–9. *(Endpoint lives under the competitors router: `/clients/{id}/competitors/provenance` — a deliberate refinement of the spec's `/clients/{id}/provenance` so it reuses `_get_client_or_404` and keeps all competitor-surface data under one router. No nav change; still admin-only.)*
- Spec §9 (language/review) → client-safe labels used in Task 9 ("Sources AI trusts…", "Where your competitors are winning attention"); admin still eyeballs the list before it informs a client deliverable.
- Spec §10 (testing) → Tasks 1,4,5,6,7,8 carry the unit/isolation/SSRF/cache/edge tests.
- Spec §3 non-goals respected: Perplexity-only (Task 4 guards `platform == "perplexity"`), no inferred sources, no client view / PDF, no backfill.

All spec requirements map to a task. No placeholders remain. Type names (`ShareOfSourceResponse`, `AcquisitionSource`, `BrandShare`, `SourcePresence`, `enrich_scan_sources`, `compute_share_of_source`, `normalize_domain`, `classify_source_type`) are consistent across backend tasks and mirrored in the frontend types.
```
