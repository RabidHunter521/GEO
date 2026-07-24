# Retainer Packaging — Monthly Report v2 + Client Work Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the monthly deliverable *prove the retainer* — a curated, client-safe delivery timeline (work log) plus six new evidence sections in the PDF, so a RM4–5k/month client sees work delivered, not just a score.

**Architecture:** A new `work_log_entries` table holds client-safe delivery records. It is **manual-first**: system events at seven existing commit points create `suggested` rows that Faris reviews, edits, and explicitly publishes — mirroring `assessment_service`'s suggest/accept trust model. Only `published` rows are ever client-visible. `report_service` gains six optional sections built from Phases 1–4 data, each independently wrapped so a failure skips its section instead of killing the report. A new public `/view/[token]/progress` tab renders the published timeline behind the existing share-token gate.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic, WeasyPrint (existing PDF pipeline), Claude (existing narrative call — context only, no new call), Next.js 15 + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-07-11-retainer-packaging-design.md`

## Global Constraints

- **Manual-first is the trust model.** `suggest()` only ever writes `status="suggested"`. Nothing reaches a client without an explicit admin publish. Manual entries (typed by Faris) are born `published` — typing it *is* the publish action.
- **Only `status="published"` is client-visible.** The client-view query filters on status **at the source**, not just in the schema. `suggested` and `dismissed` are admin-only states.
- **ActivityLog is NOT exposed to clients.** The work log is a separate, freshly-derived, born-client-safe table. Never filter/reuse ActivityLog notes for client surfaces.
- **Auto-suggest writes are best-effort and post-commit:** call `suggest()` *after* the triggering operation's `db.commit()`; `suggest()` owns its own commit and catches/rolls back/swallows its own failures. A failed suggestion must never undo or block the triggering operation (CLAUDE.md §10).
- **Idempotent suggestions:** unique partial index on `(client_id, source_ref)` where `source_ref IS NOT NULL`. Re-firing updates the existing `suggested` row's content; it **never** touches a row already `published` or `dismissed` (an edited-then-published entry is never silently reverted).
- **Language rules (CLAUDE.md §2)** on every template and every stored description — `sanitize_text` at write time, belt-and-braces. Section 5 language: "sources AI answers drew from", never "cited".
- **Report sections degrade individually.** Every `_gather_*` helper is wrapped in try/except: on failure log a structlog warning, skip that section, and still build the report. **Every section renders only when it has data — an empty phase yields no empty header.** The known "silent report failure" bug class must not grow.
- **No change to report generation/review flow:** still auto-generated, Faris reviews before sending, 30-day cadence, R2 storage (CLAUDE.md §7, §8). No weekly digest changes. No client login.
- **Admin-only** (`require_api_key`) on every new admin route; public work-log data flows only through the whitelisted client-view schema.
- **RLS enabled inline** in the migration. Current single alembic head is `dd8483cfad4a` (Phase 4) — the new migration's `down_revision`.
- **No score/dimension change, no SCORE_VERSION bump.** This phase reports work; it never scores it.
- Frontend: shadcn/ui only; admin fetches via `src/lib/api.ts`; client-view fetches via `src/lib/view-api.ts`; types in `src/types/index.ts`.
- Backend commands (this machine): poetry at `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe`, run from `backend/`. ⚠️ `backend/.env` DATABASE_URL points at PROD Supabase — **never** run `alembic upgrade`/`current`. `alembic revision`, `alembic heads`, and the SQLite test suite are safe.

## Spec Corrections (locked before implementation)

Two naming collisions found in the live codebase. The spec was written before Phases 2–4 landed:

1. **`GET /view/{token}/progress` is already taken** — it returns the *remediation loop* (`client_view.py:392`, `ClientViewProgressItem`, driven by `has_progress` on the overview). The new public work-log endpoint is therefore **`GET /view/{token}/work-log`** returning `list[ClientViewWorkLogItem]`. The **frontend route stays `/view/[token]/progress`** as the spec and CLAUDE.md §9 require (no frontend page exists at that path today, so there is no user-facing collision).
2. **`ClientViewProgressItem` is taken** → the new schema is **`ClientViewWorkLogItem`**. The existing remediation endpoint, schema, and `has_progress` flag are left completely untouched; the new overview flag is **`has_work_log`**.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/work_log_entry.py` (new) | WorkLogEntry row: category, client-safe description, source/source_ref, suggested→published lifecycle |
| `backend/app/core/constants.py` (modify) | `WORK_LOG_CATEGORIES`, `WORK_LOG_STATUSES`, `WORK_LOG_CATEGORY_LABELS` |
| `backend/alembic/versions/<generated>_add_work_log_entries.py` (new) | table + RLS + partial-unique (client_id, source_ref) |
| `backend/tests/conftest.py` (modify) | add `work_log_entry` to the model import list |
| `backend/app/services/work_log_service.py` (new) | suggest / create_manual / update_entry / list / published queries |
| `backend/app/api/v1/toolkit.py`, `site_audit_service.py`, `citability_service.py`, `deliverables.py`, `authority_service.py`, `remediation_service.py`, `scan_service.py` (modify) | 7 post-commit auto-suggest hooks |
| `backend/app/schemas/work_log.py` (new) + `backend/app/api/v1/work_log.py` (new) + `router.py` | admin CRUD routes |
| `backend/app/services/report_service.py` (modify) | 6 dataclasses + 6 `_gather_*` + 6 `_build_*_html` + assembly |
| `backend/app/prompts/report.py` (modify) | narrative gains delivered-work counts as context |
| `backend/app/api/v1/client_view.py` + `schemas/client_view.py` (modify) | `/work-log` endpoint, `ClientViewWorkLogItem`, `has_work_log` + `improvements_last_30d` on overview |
| `frontend/src/app/clients/[id]/activity/` (modify + new components) | admin work-log card (suggested queue + published timeline + add form) |
| `frontend/src/app/view/[token]/progress/page.tsx` (new) | public delivery timeline |
| `frontend/src/components/view/ViewTabs.tsx` (modify) | conditional Progress tab |
| `frontend/src/lib/api.ts`, `view-api.ts`, `types/index.ts` (modify) | API functions + types |
| `CLAUDE.md` §9 (modify) | public route list gains `/view/[token]/progress` |

---

### Task 1: WorkLogEntry model + constants + migration

**Files:**
- Create: `backend/app/models/work_log_entry.py`
- Modify: `backend/app/core/constants.py` (append)
- Modify: `backend/tests/conftest.py` (model import list)
- Create: `backend/alembic/versions/<generated>_add_work_log_entries.py`
- Test: `backend/tests/test_work_log_models.py`

**Interfaces:**
- Produces: `WorkLogEntry(id, client_id, category, description, source, source_ref, status="suggested", entry_date, created_at, published_at)`; constants `WORK_LOG_CATEGORIES`, `WORK_LOG_STATUSES`, `WORK_LOG_CATEGORY_LABELS`.

- [ ] **Step 1: Add the constants**

Append to `backend/app/core/constants.py`:

```python
# --- Retainer packaging: client work log (Phase 5) --------------------------
# Manual-first delivery timeline. Auto-triggers write "suggested" rows only;
# nothing is client-visible until the admin explicitly publishes it.
WORK_LOG_CATEGORIES: Final = ("technical", "content", "authority", "visibility", "correction")
WORK_LOG_STATUSES: Final = ("suggested", "published", "dismissed")
WORK_LOG_CATEGORY_LABELS: Final = {
    "technical":  "Technical",
    "content":    "Content",
    "authority":  "Authority",
    "visibility": "Visibility",
    "correction": "Correction",
}
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_work_log_models.py`:

```python
"""WorkLogEntry persistence (spec §3.2)."""
from datetime import date


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_work_log_entry_defaults(db):
    from app.models.work_log_entry import WorkLogEntry
    client = _make_client(db)
    e = WorkLogEntry(
        client_id=client.id, category="technical",
        description="Published and verified llms.txt so AI systems can read your site",
        source="auto", source_ref="toolkit_verified:llms", entry_date=date(2026, 7, 24),
    )
    db.add(e)
    db.commit()
    row = db.query(WorkLogEntry).one()
    assert row.status == "suggested"
    assert row.published_at is None
    assert row.created_at is not None
    assert row.entry_date == date(2026, 7, 24)


def test_manual_entry_has_null_source_ref(db):
    from app.models.work_log_entry import WorkLogEntry
    client = _make_client(db)
    e = WorkLogEntry(
        client_id=client.id, category="authority",
        description="Submitted your business to three local directories",
        source="manual", source_ref=None, entry_date=date(2026, 7, 24),
        status="published",
    )
    db.add(e)
    db.commit()
    row = db.query(WorkLogEntry).one()
    assert row.source_ref is None
    assert row.status == "published"
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `backend/`): `poetry run pytest tests/test_work_log_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.work_log_entry'`

- [ ] **Step 4: Create the model**

`backend/app/models/work_log_entry.py`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class WorkLogEntry(Base):
    """One client-safe record of work delivered.

    Born client-safe (unlike ActivityLog, whose notes use internal admin
    vocabulary and must never reach a client). Manual-first: auto-triggers
    write status="suggested" only; the admin reviews, edits, and publishes.
    ONLY status="published" is ever client-visible. See
    docs/superpowers/specs/2026-07-11-retainer-packaging-design.md.
    """

    __tablename__ = "work_log_entries"
    __table_args__ = (
        # Idempotent auto-suggestions: one row per (client, triggering event).
        # Manual entries (NULL source_ref) are unconstrained.
        Index(
            "uq_work_log_entries_client_source_ref", "client_id", "source_ref", unique=True,
            postgresql_where=text("source_ref IS NOT NULL"),
            sqlite_where=text("source_ref IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # technical | content | authority | visibility | correction
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # Client-safe text, sanitized at write time; admin-editable before publish.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # auto | manual
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto", server_default="auto")
    # "<event>:<entity id>" — dedupe key for auto suggestions. NULL for manual.
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # suggested | published | dismissed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="suggested", server_default="suggested"
    )
    # When the work happened (editable pre-publish) — drives report period filtering.
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 5: Register the model in conftest**

In `backend/tests/conftest.py`, append `, work_log_entry` to the end of the long `from app.models import ...` line, immediately before the `  # noqa: F401`:

```python
... site_audit, page_audit, content_deliverable, authority_asset, work_log_entry  # noqa: F401
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest tests/test_work_log_models.py -q`
Expected: 2 passed.

- [ ] **Step 7: Create the migration**

Run: `poetry run alembic revision -m "add work log entries"` (from `backend/`; applies nothing). Keep the generated revision ID; replace the file body with (substituting `<generated>`):

```python
"""add work log entries

Revision ID: <generated>
Revises: dd8483cfad4a
Create Date: <keep generated date>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<generated>'
down_revision: Union[str, None] = 'dd8483cfad4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_log_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="auto"),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="suggested"),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_log_entries_client_id", "work_log_entries", ["client_id"])
    op.create_index(
        "uq_work_log_entries_client_source_ref", "work_log_entries", ["client_id", "source_ref"],
        unique=True, postgresql_where=sa.text("source_ref IS NOT NULL"),
    )
    op.execute("ALTER TABLE work_log_entries ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE work_log_entries DISABLE ROW LEVEL SECURITY;")
    op.drop_index("uq_work_log_entries_client_source_ref", table_name="work_log_entries")
    op.drop_index("ix_work_log_entries_client_id", table_name="work_log_entries")
    op.drop_table("work_log_entries")
```

- [ ] **Step 8: Verify the migration chain (seenby-migrations gate)**

```bash
poetry run alembic heads
```
Expected: exactly ONE head — the new revision ID.

```bash
grep -rn "^revision" alembic/versions/ | sort | uniq -d -f1
```
Expected: no output. **Do NOT run `alembic upgrade`** — `.env` points at prod.

- [ ] **Step 9: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass (762 baseline + 2 new).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/work_log_entry.py backend/app/core/constants.py backend/tests/conftest.py backend/tests/test_work_log_models.py backend/alembic/versions/
git commit -m "feat(work-log): WorkLogEntry model + constants + migration"
```

---

### Task 2: work_log_service core

**Files:**
- Create: `backend/app/services/work_log_service.py`
- Test: `backend/tests/test_work_log_service.py`

**Interfaces:**
- Produces:
  - `suggest(client_id: uuid.UUID, category: str, description: str, source_ref: str, db: Session, entry_date: date | None = None) -> WorkLogEntry | None` — best-effort, post-commit, owns its own commit. Creates or updates a `suggested` row keyed by `(client_id, source_ref)`. **Never** touches a row already `published` or `dismissed` (returns it unchanged). Returns None on any failure (caught, rolled back, swallowed).
  - `create_manual(client_id: uuid.UUID, category: str, description: str, entry_date: date, db: Session) -> WorkLogEntry` — `source="manual"`, `status="published"`, `published_at` set. Raises `ValueError` on an unknown category.
  - `update_entry(entry: WorkLogEntry, patch: dict, db: Session) -> WorkLogEntry` — applies `description`/`category`/`entry_date`, and `status` transitions (`suggested→published` sets `published_at`; `suggested→dismissed`; `published→dismissed` as undo, clearing `published_at`). Unknown category/status values are ignored.
  - `list_entries(client_id: uuid.UUID, db: Session, status: str | None = None) -> list[WorkLogEntry]` — newest `entry_date` first, then `created_at` desc.
  - `published_entries(client_id: uuid.UUID, db: Session, since: date | None = None, until: date | None = None) -> list[WorkLogEntry]` — `status="published"` only, `entry_date` window inclusive, newest first.
  - `published_count_since(client_id: uuid.UUID, db: Session, since: date) -> int`.
- Consumes: `WorkLogEntry`; `WORK_LOG_CATEGORIES`, `WORK_LOG_STATUSES` from constants; `sanitize_text` from `language_sanitizer`; `utcnow` from `app.core.time`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_work_log_service.py`:

```python
"""work_log_service — manual-first lifecycle (spec §3.2-3.3, §7)."""
from datetime import date, timedelta


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


# 1. Auto-suggestion idempotence: same source_ref twice → one row, updated.
def test_suggest_is_idempotent_and_updates(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    work_log_service.suggest(client.id, "technical", "First text", "toolkit_verified:llms", db)
    work_log_service.suggest(client.id, "technical", "Second text", "toolkit_verified:llms", db)
    rows = db.query(WorkLogEntry).all()
    assert len(rows) == 1
    assert rows[0].description == "Second text"
    assert rows[0].status == "suggested"


# 1b. Re-firing after publish/dismiss leaves the reviewed row untouched.
def test_suggest_never_regresses_published_or_dismissed(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.suggest(client.id, "technical", "Original", "ref:1", db)
    work_log_service.update_entry(entry, {"description": "Edited by admin", "status": "published"}, db)
    work_log_service.suggest(client.id, "technical", "Template text again", "ref:1", db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == "ref:1").one()
    assert row.description == "Edited by admin"
    assert row.status == "published"

    dismissed = work_log_service.suggest(client.id, "content", "D", "ref:2", db)
    work_log_service.update_entry(dismissed, {"status": "dismissed"}, db)
    work_log_service.suggest(client.id, "content", "D again", "ref:2", db)
    row2 = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == "ref:2").one()
    assert row2.status == "dismissed"


# 2. Sanitizer applied at write time.
def test_suggest_sanitizes_banned_language(db):
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.suggest(
        client.id, "visibility", "You are now cited by ChatGPT", "ref:san", db)
    assert "cited" not in entry.description
    assert "seen by AI" in entry.description


# 4. Manual entries are published immediately, no review step.
def test_create_manual_is_published_immediately(db):
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.create_manual(
        client.id, "authority", "Submitted your business to three directories",
        date(2026, 7, 24), db)
    assert entry.status == "published"
    assert entry.published_at is not None
    assert entry.source == "manual"
    assert entry.source_ref is None


# 5. Status transitions.
def test_status_transitions(db):
    from app.services import work_log_service
    client = _make_client(db)
    e = work_log_service.suggest(client.id, "technical", "T", "ref:t", db)
    assert e.published_at is None
    work_log_service.update_entry(e, {"status": "published"}, db)
    assert e.status == "published" and e.published_at is not None
    work_log_service.update_entry(e, {"status": "dismissed"}, db)   # undo after publish
    assert e.status == "dismissed" and e.published_at is None


# 6. Editing a suggested row's description before publish persists the edit.
def test_edit_before_publish_persists(db):
    from app.services import work_log_service
    client = _make_client(db)
    e = work_log_service.suggest(client.id, "content", "Template", "ref:e", db)
    work_log_service.update_entry(e, {"description": "Faris's better wording"}, db)
    assert e.description == "Faris's better wording"


def test_published_entries_filters_status_and_window(db):
    from app.services import work_log_service
    client = _make_client(db)
    today = date(2026, 7, 24)
    inside = work_log_service.suggest(client.id, "technical", "Inside", "ref:in", db, entry_date=today)
    work_log_service.update_entry(inside, {"status": "published"}, db)
    outside = work_log_service.suggest(
        client.id, "technical", "Outside", "ref:out", db, entry_date=today - timedelta(days=60))
    work_log_service.update_entry(outside, {"status": "published"}, db)
    work_log_service.suggest(client.id, "technical", "Still suggested", "ref:sug", db, entry_date=today)

    published = work_log_service.published_entries(client.id, db, since=today - timedelta(days=30))
    descriptions = [p.description for p in published]
    assert "Inside" in descriptions
    assert "Outside" not in descriptions      # outside the window
    assert "Still suggested" not in descriptions  # not published
    assert work_log_service.published_count_since(client.id, db, today - timedelta(days=30)) == 1


def test_create_manual_rejects_unknown_category(db):
    import pytest
    from app.services import work_log_service
    client = _make_client(db)
    with pytest.raises(ValueError):
        work_log_service.create_manual(client.id, "bogus", "x", date(2026, 7, 24), db)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_work_log_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.work_log_service'`

- [ ] **Step 3: Implement the service**

`backend/app/services/work_log_service.py`:

```python
"""Client work log — the client-safe delivery timeline (spec §3).

Manual-first by design: auto-triggers only ever write `suggested` rows that
the admin reviews, edits, and explicitly publishes. Only `published` rows are
client-visible. Every description is sanitized at write time (CLAUDE.md §2)
even though the admin also sees and can edit it before publishing.
"""
import uuid
from datetime import date

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import WORK_LOG_CATEGORIES, WORK_LOG_STATUSES
from app.core.time import utcnow
from app.models.work_log_entry import WorkLogEntry
from app.services.language_sanitizer import sanitize_text

logger = structlog.get_logger()


def suggest(
    client_id: uuid.UUID,
    category: str,
    description: str,
    source_ref: str,
    db: Session,
    entry_date: date | None = None,
) -> WorkLogEntry | None:
    """Create or refresh a `suggested` work-log row for a system event.

    BEST-EFFORT + POST-COMMIT: call this AFTER the triggering operation has
    committed. It owns its own commit and swallows its own failures, so a
    problem here can never undo the work that triggered it (CLAUDE.md §10).

    Idempotent on (client_id, source_ref). A row that the admin has already
    published or dismissed is returned untouched — a re-fired trigger must
    never revert a reviewed decision or overwrite edited wording.
    """
    try:
        if category not in WORK_LOG_CATEGORIES:
            return None
        existing = (
            db.query(WorkLogEntry)
            .filter(WorkLogEntry.client_id == client_id, WorkLogEntry.source_ref == source_ref)
            .first()
        )
        if existing is not None:
            if existing.status != "suggested":
                return existing  # reviewed already — hands off
            existing.description = sanitize_text(description)
            existing.category = category
            if entry_date is not None:
                existing.entry_date = entry_date
            db.commit()
            db.refresh(existing)
            return existing

        entry = WorkLogEntry(
            client_id=client_id,
            category=category,
            description=sanitize_text(description),
            source="auto",
            source_ref=source_ref,
            status="suggested",
            entry_date=entry_date or utcnow().date(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as exc:
        db.rollback()
        logger.warning(
            "work_log_suggest_failed",
            client_id=str(client_id), source_ref=source_ref, error=str(exc),
        )
        return None


def create_manual(
    client_id: uuid.UUID, category: str, description: str, entry_date: date, db: Session
) -> WorkLogEntry:
    """A manual entry is born published — typing it IS the publish action."""
    if category not in WORK_LOG_CATEGORIES:
        raise ValueError(f"unknown work-log category: {category}")
    entry = WorkLogEntry(
        client_id=client_id,
        category=category,
        description=sanitize_text(description),
        source="manual",
        source_ref=None,
        status="published",
        entry_date=entry_date,
        published_at=utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(entry: WorkLogEntry, patch: dict, db: Session) -> WorkLogEntry:
    """Edit content and/or move status. Editing is allowed after publish so a
    mistake can still be corrected; `published → dismissed` is the undo."""
    if "description" in patch and patch["description"]:
        entry.description = sanitize_text(patch["description"])
    if "category" in patch and patch["category"] in WORK_LOG_CATEGORIES:
        entry.category = patch["category"]
    if "entry_date" in patch and patch["entry_date"]:
        entry.entry_date = patch["entry_date"]
    if "status" in patch and patch["status"] in WORK_LOG_STATUSES:
        new_status = patch["status"]
        if new_status != entry.status:
            entry.status = new_status
            entry.published_at = utcnow() if new_status == "published" else None
    db.commit()
    db.refresh(entry)
    return entry


def list_entries(
    client_id: uuid.UUID, db: Session, status: str | None = None
) -> list[WorkLogEntry]:
    q = db.query(WorkLogEntry).filter(WorkLogEntry.client_id == client_id)
    if status:
        q = q.filter(WorkLogEntry.status == status)
    return q.order_by(desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at)).all()


def published_entries(
    client_id: uuid.UUID, db: Session, since: date | None = None, until: date | None = None
) -> list[WorkLogEntry]:
    """Published rows only — the single source of client-visible truth.

    Status is filtered HERE, at the query, not merely omitted from a schema,
    so a `suggested` row can never leak client-side (spec §3.5).
    """
    q = db.query(WorkLogEntry).filter(
        WorkLogEntry.client_id == client_id, WorkLogEntry.status == "published"
    )
    if since is not None:
        q = q.filter(WorkLogEntry.entry_date >= since)
    if until is not None:
        q = q.filter(WorkLogEntry.entry_date <= until)
    return q.order_by(desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at)).all()


def published_count_since(client_id: uuid.UUID, db: Session, since: date) -> int:
    return (
        db.query(WorkLogEntry)
        .filter(
            WorkLogEntry.client_id == client_id,
            WorkLogEntry.status == "published",
            WorkLogEntry.entry_date >= since,
        )
        .count()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_work_log_service.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_log_service.py backend/tests/test_work_log_service.py
git commit -m "feat(work-log): suggest/publish lifecycle service"
```

---

### Task 3: Auto-suggest hooks at the seven trigger points

**Files:**
- Modify: `backend/app/api/v1/toolkit.py` (after the `toolkit_verified` commit, ~line 130)
- Modify: `backend/app/services/site_audit_service.py` (after the `site_audit_run` commit, ~line 622)
- Modify: `backend/app/services/citability_service.py` (after `audit_page`'s commit, ~line 400)
- Modify: `backend/app/api/v1/deliverables.py` (after the `deliverable_reviewed` commit, ~line 87)
- Modify: `backend/app/services/authority_service.py` (after `update_asset` / `verify_asset` commits)
- Modify: `backend/app/services/remediation_service.py` (after `set_remediation_status` commit)
- Modify: `backend/app/services/scan_service.py` (post-commit block, alongside the existing provenance steps)
- Test: `backend/tests/test_work_log_hooks.py`

**Interfaces:**
- Consumes: `work_log_service.suggest` (Task 2).
- Produces: `work_log_service.suggest_query_flips(client_id, db) -> int` (number of suggestions written) — reads `scan_diff_service.compute_scan_diff` for `newly_seen` and writes one `visibility` suggestion per flipped query (max 5).

**Source-ref conventions (must be exact — they are the dedupe keys):**

| Trigger | Category | `source_ref` | Template |
|---|---|---|---|
| toolkit file verified | technical | `toolkit_verified:{file_type}` | `Published and verified {file} so AI systems can read your site` |
| site audit, n fixed | technical | `site_audit:{audit_id}` | `Technical AI-readiness check: {n} issues fixed since last audit` (only when n>0) |
| page audit improved | content | `page_audit:{audit_id}` | `Improved AI-readability of {path}: {old} → {new}` |
| deliverable reviewed | content | `deliverable:{deliverable_id}` | `Delivered: {title}` |
| authority live/verified | authority | `authority_{status}:{asset_id}` | `Your {name} profile is now live` / `Your {name} profile is now verified` |
| remediation corrected | correction | `remediation:{item_id}` | `Corrected: {label}` |
| query flipped to seen | visibility | `query_flip:{platform}:{query_text[:60]}` | `Now seen by AI for: "{query_text}"` |

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_work_log_hooks.py`:

```python
"""Auto-suggest hooks (spec §3.3). Each writes a `suggested` row post-commit
and is best-effort — a failure must never undo the triggering operation."""
from datetime import date
from unittest.mock import patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


# 3. A failure inside suggest() does not roll back the triggering commit.
def test_suggest_failure_does_not_undo_trigger(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service, work_log_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    with patch.object(work_log_service, "suggest", side_effect=Exception("boom")):
        # The status change must still commit even though the hook explodes.
        try:
            authority_service.update_asset(asset, {"status": "live"}, db)
        except Exception:
            db.rollback()
    db.expire_all()
    assert db.query(AuthorityAsset).one().status == "live"


def test_authority_live_writes_suggestion(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "authority").one()
    assert row.status == "suggested"
    assert row.source_ref == f"authority_live:{asset.id}"
    assert "Google Business Profile" in row.description
    assert "live" in row.description


def test_authority_missing_status_writes_nothing(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "in_progress"}, db)
    assert db.query(WorkLogEntry).count() == 0


def test_remediation_corrected_writes_suggestion(db):
    from app.models.remediation_item import RemediationItem
    from app.models.work_log_entry import WorkLogEntry
    from app.services import remediation_service
    client = _make_client(db)
    item = RemediationItem(
        client_id=client.id, item_type="content_gap", platform="chatgpt",
        label="best dental clinic in KL", status="flagged",
    )
    db.add(item)
    db.commit()
    remediation_service.set_remediation_status(item, "corrected", db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "correction").one()
    assert row.source_ref == f"remediation:{item.id}"
    assert "best dental clinic in KL" in row.description


def test_query_flips_write_visibility_suggestions(db):
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    older = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(older)
    db.commit()
    newer = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(newer)
    db.commit()
    for scan, detected in ((older, False), (newer, True)):
        db.add(ScanQueryResult(
            scan_id=scan.id, platform="chatgpt", category="recommendation",
            query_text="best dental clinic in KL", response_text="...",
            brand_detected=detected,
        ))
    db.commit()
    written = work_log_service.suggest_query_flips(client.id, db)
    assert written == 1
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "visibility").one()
    assert "best dental clinic in KL" in row.description
    assert row.status == "suggested"
```

Note: if `RemediationItem` or `Scan` require additional non-null fields, copy the minimal construction from an existing test (grep `RemediationItem(` / `Scan(` in `backend/tests/`). Do not invent columns.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_work_log_hooks.py -q`
Expected: FAIL — no work-log rows written (hooks not wired), and `AttributeError: ... 'suggest_query_flips'`.

- [ ] **Step 3: Add `suggest_query_flips` to work_log_service**

Append to `backend/app/services/work_log_service.py`:

```python
_MAX_FLIP_SUGGESTIONS = 5


def suggest_query_flips(client_id: uuid.UUID, db: Session) -> int:
    """One `visibility` suggestion per query that flipped to Seen by AI.

    Reads the existing scan-to-scan diff so the wording matches what the rest
    of the product already computes. Best-effort like every other suggestion.
    """
    try:
        from app.services.scan_diff_service import compute_scan_diff
        diff = compute_scan_diff(client_id, db)
    except Exception as exc:
        logger.warning("work_log_flip_diff_failed", client_id=str(client_id), error=str(exc))
        return 0
    written = 0
    for q in (diff.newly_seen or [])[:_MAX_FLIP_SUGGESTIONS]:
        entry = suggest(
            client_id,
            "visibility",
            f'Now seen by AI for: "{q.query_text}"',
            f"query_flip:{q.platform}:{q.query_text[:60]}",
            db,
        )
        if entry is not None:
            written += 1
    return written
```

- [ ] **Step 4: Wire the seven hooks**

Each hook goes **after** the triggering `db.commit()`, wrapped so it can never raise into the caller.

**4a. `backend/app/services/authority_service.py`** — in `update_asset`, after `db.refresh(asset)` and before `return asset`:

```python
    if status_changed and asset.status in ("live", "verified"):
        try:
            from app.services import work_log_service
            work_log_service.suggest(
                asset.client_id, "authority",
                f"Your {asset.name} profile is now {asset.status}",
                f"authority_{asset.status}:{asset.id}", db,
            )
        except Exception:  # never let a suggestion undo a saved status change
            db.rollback()
```

In `verify_asset`, after `db.refresh(asset)` and before `return asset, note`, add the same block guarded on the verified transition:

```python
    if asset.status == "verified":
        try:
            from app.services import work_log_service
            work_log_service.suggest(
                asset.client_id, "authority",
                f"Your {asset.name} profile is now verified",
                f"authority_verified:{asset.id}", db,
            )
        except Exception:
            db.rollback()
```

**4b. `backend/app/services/remediation_service.py`** — in `set_remediation_status`, after its `db.commit()`:

```python
    if status == "corrected":
        try:
            from app.services import work_log_service
            work_log_service.suggest(
                item.client_id, "correction", f"Corrected: {item.label}",
                f"remediation:{item.id}", db,
            )
        except Exception:
            db.rollback()
```

**4c. `backend/app/api/v1/toolkit.py`** — after the `toolkit_verified` ActivityLog commit (~line 130), for each file type that verified true:

```python
    try:
        from app.services import work_log_service
        for file_type, ok in verified_map.items():
            if ok:
                work_log_service.suggest(
                    client.id, "technical",
                    f"Published and verified {file_type} so AI systems can read your site",
                    f"toolkit_verified:{file_type}", db,
                )
    except Exception:
        db.rollback()
```

Adapt `verified_map` to the actual local variable holding per-file verification results in that handler (read the surrounding code; if the handler verifies a single file, write one suggestion using that file's name).

**4d. `backend/app/services/site_audit_service.py`** — after the `site_audit_run` commit, when the count of checks fixed since the previous audit is > 0:

```python
    try:
        if fixed_count > 0:
            from app.services import work_log_service
            work_log_service.suggest(
                client_id, "technical",
                f"Technical AI-readiness check: {fixed_count} issues fixed since last audit",
                f"site_audit:{audit.id}", db,
            )
    except Exception:
        db.rollback()
```

Compute `fixed_count` by comparing this audit's failed/warned check ids against the previous audit's — if the service already computes such a delta, reuse it rather than recomputing. If no previous audit exists, skip (no suggestion).

**4e. `backend/app/services/citability_service.py`** — in `audit_page`, after `db.refresh(audit)`, when a previous audit of the same URL scored lower:

```python
    try:
        from urllib.parse import urlparse
        previous = (
            db.query(PageAudit)
            .filter(PageAudit.client_id == client.id, PageAudit.url == normalized,
                    PageAudit.id != audit.id)
            .order_by(PageAudit.created_at.desc())
            .first()
        )
        if previous is not None and audit.score > previous.score:
            from app.services import work_log_service
            path = urlparse(normalized).path or "/"
            work_log_service.suggest(
                client.id, "content",
                f"Improved AI-readability of {path}: {previous.score} → {audit.score}",
                f"page_audit:{audit.id}", db,
            )
    except Exception:
        db.rollback()
```

**4f. `backend/app/api/v1/deliverables.py`** — after the `deliverable_reviewed` commit (~line 87):

```python
    try:
        from app.services import work_log_service
        work_log_service.suggest(
            client_id, "content", f"Delivered: {deliverable.title}",
            f"deliverable:{deliverable.id}", db,
        )
    except Exception:
        db.rollback()
```

**4g. `backend/app/services/scan_service.py`** — in `run_scan`'s post-commit best-effort block, after the existing `compute_and_persist_snapshot(...)` call, matching its isolation style:

```python
    try:
        from app.services import work_log_service
        work_log_service.suggest_query_flips(client.id, db)
    except Exception as exc:
        db.rollback()
        logger.error("work_log_flip_suggestions_failed", scan_id=str(scan.id), error=str(exc))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/test_work_log_hooks.py tests/test_work_log_service.py -q`
Expected: all pass (5 hook tests + 8 service tests).

- [ ] **Step 6: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass. If a pre-existing test now sees an extra work-log row, that is expected behaviour — update the assertion only if it counted rows in a table this phase legitimately writes to; never weaken an unrelated assertion.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/work_log_service.py backend/app/services/authority_service.py backend/app/services/remediation_service.py backend/app/services/site_audit_service.py backend/app/services/citability_service.py backend/app/services/scan_service.py backend/app/api/v1/toolkit.py backend/app/api/v1/deliverables.py backend/tests/test_work_log_hooks.py
git commit -m "feat(work-log): auto-suggest hooks at seven delivery trigger points"
```

---

### Task 4: Admin API + schemas

**Files:**
- Create: `backend/app/schemas/work_log.py`
- Create: `backend/app/api/v1/work_log.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_work_log_api.py`

**Interfaces:**
- Produces (all admin-only, `require_api_key`):
  - `GET /api/v1/clients/{id}/work-log?status=` → `list[WorkLogEntryOut]`
  - `POST /api/v1/clients/{id}/work-log` → `WorkLogEntryOut` (manual entry, published immediately)
  - `PATCH /api/v1/clients/{id}/work-log/{entry_id}` → `WorkLogEntryOut`
- Consumes: Task 2 service functions.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_work_log_api.py`:

```python
"""work-log admin API (spec §3.4). Mirrors test_authority_api.py's fixtures —
open that file and reuse its exact `client` / `auth_headers` fixture pattern."""
import uuid
from datetime import date


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_list_empty(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/work-log", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_manual_entry_is_published(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(
        f"/api/v1/clients/{c.id}/work-log", headers=auth_headers,
        json={"category": "authority", "description": "Submitted to three directories",
              "entry_date": "2026-07-24"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published"
    assert body["source"] == "manual"


def test_publish_and_dismiss_transitions(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    entry = work_log_service.suggest(c.id, "technical", "Verified llms.txt", "ref:api", db)
    r = client.patch(f"/api/v1/clients/{c.id}/work-log/{entry.id}", headers=auth_headers,
                     json={"status": "published", "description": "Edited wording"})
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["description"] == "Edited wording"
    r2 = client.patch(f"/api/v1/clients/{c.id}/work-log/{entry.id}", headers=auth_headers,
                      json={"status": "dismissed"})
    assert r2.json()["status"] == "dismissed"


def test_status_filter(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    work_log_service.suggest(c.id, "technical", "S", "ref:s", db)
    work_log_service.create_manual(c.id, "content", "P", date(2026, 7, 24), db)
    suggested = client.get(f"/api/v1/clients/{c.id}/work-log?status=suggested",
                           headers=auth_headers).json()
    assert len(suggested) == 1 and suggested[0]["description"] == "S"


def test_unknown_category_rejected(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(f"/api/v1/clients/{c.id}/work-log", headers=auth_headers,
                    json={"category": "bogus", "description": "x", "entry_date": "2026-07-24"})
    assert r.status_code == 422


def test_requires_auth(client, db):
    c = _make_client(db)
    assert client.get(f"/api/v1/clients/{c.id}/work-log").status_code in (401, 403)


def test_patch_unknown_entry_404s(client, db, auth_headers):
    c = _make_client(db)
    r = client.patch(f"/api/v1/clients/{c.id}/work-log/{uuid.uuid4()}",
                     headers=auth_headers, json={"status": "published"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_work_log_api.py -q`
Expected: FAIL — 404s (router not wired).

- [ ] **Step 3: Implement the schemas**

`backend/app/schemas/work_log.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class WorkLogEntryOut(BaseModel):
    id: uuid.UUID
    category: str
    category_label: str
    description: str
    source: str
    status: str
    entry_date: date
    created_at: datetime
    published_at: datetime | None

    model_config = {"from_attributes": True}


class WorkLogCreateRequest(BaseModel):
    category: str
    description: str
    entry_date: date


class WorkLogPatchRequest(BaseModel):
    category: str | None = None
    description: str | None = None
    entry_date: date | None = None
    status: str | None = None
```

- [ ] **Step 4: Implement the routes**

`backend/app/api/v1/work_log.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import (
    WORK_LOG_CATEGORIES,
    WORK_LOG_CATEGORY_LABELS,
    WORK_LOG_STATUSES,
)
from app.core.database import get_db
from app.models.client import Client
from app.models.work_log_entry import WorkLogEntry
from app.schemas.work_log import WorkLogCreateRequest, WorkLogEntryOut, WorkLogPatchRequest
from app.services import work_log_service

router = APIRouter(prefix="/clients/{client_id}/work-log", tags=["work-log"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _out(entry: WorkLogEntry) -> WorkLogEntryOut:
    data = WorkLogEntryOut.model_validate(entry)
    data.category_label = WORK_LOG_CATEGORY_LABELS.get(entry.category, entry.category.title())
    return data


@router.get("", response_model=list[WorkLogEntryOut], dependencies=[Depends(require_api_key)])
def list_work_log(
    client_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    if status is not None and status not in WORK_LOG_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    return [_out(e) for e in work_log_service.list_entries(client_id, db, status=status)]


@router.post("", response_model=WorkLogEntryOut, dependencies=[Depends(require_api_key)])
def create_work_log(
    client_id: uuid.UUID, body: WorkLogCreateRequest, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    if body.category not in WORK_LOG_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")
    if not body.description.strip():
        raise HTTPException(status_code=422, detail="Description is required.")
    entry = work_log_service.create_manual(
        client_id, body.category, body.description, body.entry_date, db
    )
    return _out(entry)


@router.patch("/{entry_id}", response_model=WorkLogEntryOut, dependencies=[Depends(require_api_key)])
def patch_work_log(
    client_id: uuid.UUID, entry_id: uuid.UUID, body: WorkLogPatchRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    entry = db.get(WorkLogEntry, entry_id)
    if not entry or entry.client_id != client_id:
        raise HTTPException(status_code=404, detail="Entry not found")
    patch = body.model_dump(exclude_unset=True)
    if "category" in patch and patch["category"] not in WORK_LOG_CATEGORIES:
        raise HTTPException(status_code=422, detail="Unknown category.")
    if "status" in patch and patch["status"] not in WORK_LOG_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    return _out(work_log_service.update_entry(entry, patch, db))
```

`WorkLogEntryOut.category_label` has no default, so give it one in the schema to allow `model_validate` before assignment — change the field to `category_label: str = ""` in `backend/app/schemas/work_log.py`.

In `backend/app/api/v1/router.py`: add `work_log` to the `from app.api.v1 import ...` line and `router.include_router(work_log.router)` at the end.

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/test_work_log_api.py -q`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/work_log.py backend/app/api/v1/work_log.py backend/app/api/v1/router.py backend/tests/test_work_log_api.py
git commit -m "feat(work-log): admin CRUD API + schemas"
```

---

### Task 5: Admin work-log card on the activity page

**Files:**
- Create: `frontend/src/app/clients/[id]/activity/WorkLogCard.tsx`
- Create: `frontend/src/app/clients/[id]/activity/actions.ts`
- Modify: `frontend/src/app/clients/[id]/activity/page.tsx`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`

**Interfaces:**
- Consumes: Task 4 routes.

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```typescript
// --- Client work log (Phase 5) ---
export type WorkLogCategory =
  | "technical" | "content" | "authority" | "visibility" | "correction"
export type WorkLogStatus = "suggested" | "published" | "dismissed"

export interface WorkLogEntry {
  id: string
  category: WorkLogCategory
  category_label: string
  description: string
  source: "auto" | "manual"
  status: WorkLogStatus
  entry_date: string
  created_at: string
  published_at: string | null
}
```

- [ ] **Step 2: Add api.ts functions**

Append to `frontend/src/lib/api.ts` (and add `WorkLogEntry`, `WorkLogCategory`, `WorkLogStatus` to the `import type` block):

```typescript
export async function getWorkLog(
  clientId: string, status?: WorkLogStatus,
): Promise<WorkLogEntry[]> {
  const q = status ? `?status=${status}` : ""
  return apiFetch<WorkLogEntry[]>(`/api/v1/clients/${clientId}/work-log${q}`)
}
export async function createWorkLogEntry(
  clientId: string, body: { category: WorkLogCategory; description: string; entry_date: string },
): Promise<WorkLogEntry> {
  return apiFetch<WorkLogEntry>(`/api/v1/clients/${clientId}/work-log`, {
    method: "POST", body: JSON.stringify(body),
  })
}
export async function patchWorkLogEntry(
  clientId: string, entryId: string,
  patch: { category?: WorkLogCategory; description?: string; entry_date?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  return apiFetch<WorkLogEntry>(`/api/v1/clients/${clientId}/work-log/${entryId}`, {
    method: "PATCH", body: JSON.stringify(patch),
  })
}
```

- [ ] **Step 3: Server actions**

`frontend/src/app/clients/[id]/activity/actions.ts`:

```typescript
"use server"

import { revalidatePath } from "next/cache"
import { createWorkLogEntry, patchWorkLogEntry } from "@/lib/api"
import type { WorkLogCategory, WorkLogEntry, WorkLogStatus } from "@/types"

const path = (clientId: string) => `/clients/${clientId}/activity`

export async function createWorkLogAction(
  clientId: string,
  body: { category: WorkLogCategory; description: string; entry_date: string },
): Promise<WorkLogEntry> {
  const entry = await createWorkLogEntry(clientId, body)
  revalidatePath(path(clientId))
  return entry
}

export async function patchWorkLogAction(
  clientId: string,
  entryId: string,
  patch: { description?: string; category?: WorkLogCategory; entry_date?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  const entry = await patchWorkLogEntry(clientId, entryId, patch)
  revalidatePath(path(clientId))
  return entry
}
```

- [ ] **Step 4: Build the card**

`frontend/src/app/clients/[id]/activity/WorkLogCard.tsx`:

```typescript
"use client"

import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import type { WorkLogCategory, WorkLogEntry } from "@/types"
import { createWorkLogAction, patchWorkLogAction } from "./actions"

const CATEGORIES: WorkLogCategory[] = [
  "technical", "content", "authority", "visibility", "correction",
]

export function WorkLogCard({
  clientId, initialEntries,
}: { clientId: string; initialEntries: WorkLogEntry[] }) {
  const [entries, setEntries] = useState(initialEntries)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState({
    category: "technical" as WorkLogCategory,
    description: "",
    entry_date: new Date().toISOString().slice(0, 10),
  })

  const suggested = entries.filter((e) => e.status === "suggested")
  const published = entries.filter((e) => e.status === "published")

  async function run<T>(fn: () => Promise<T>) {
    setPending(true)
    setError(null)
    try {
      return await fn()
    } catch {
      setError("Couldn't save that — please try again.")
    } finally {
      setPending(false)
    }
  }

  function replace(updated: WorkLogEntry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-base">Work log</CardTitle>
        <p className="text-sm text-muted-foreground">
          What the client sees as work delivered. Nothing here reaches a client until you publish it.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Suggested ({suggested.length})</h3>
          {suggested.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing waiting for review.</p>
          ) : (
            suggested.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2.5">
                <Badge variant="outline">{e.category_label}</Badge>
                <Input
                  defaultValue={e.description}
                  className="min-w-[16rem] flex-1"
                  onBlur={(ev) =>
                    ev.target.value !== e.description &&
                    run(async () => replace(await patchWorkLogAction(clientId, e.id, { description: ev.target.value })))
                  }
                />
                <span className="text-xs text-muted-foreground">{e.entry_date}</span>
                <Button size="sm" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "published" })))}>
                  Publish
                </Button>
                <Button size="sm" variant="ghost" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "dismissed" })))}>
                  Dismiss
                </Button>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-medium">Published ({published.length})</h3>
          {published.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing published yet.</p>
          ) : (
            published.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2.5">
                <Badge variant="secondary">{e.category_label}</Badge>
                <span className="min-w-[16rem] flex-1 text-sm">{e.description}</span>
                <span className="text-xs text-muted-foreground">{e.entry_date}</span>
                <Button size="sm" variant="ghost" disabled={pending}
                        onClick={() => run(async () => replace(await patchWorkLogAction(clientId, e.id, { status: "dismissed" })))}>
                  Unpublish
                </Button>
              </div>
            ))
          )}
        </div>

        <div className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Add an entry</h3>
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-40">
              <Select value={draft.category}
                      onValueChange={(v) => setDraft({ ...draft, category: v as WorkLogCategory })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Input placeholder="What did you deliver?" className="min-w-[16rem] flex-1"
                   value={draft.description}
                   onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            <Input type="date" className="w-40" value={draft.entry_date}
                   onChange={(e) => setDraft({ ...draft, entry_date: e.target.value })} />
            <Button size="sm" disabled={pending || !draft.description.trim()}
                    onClick={() =>
                      run(async () => {
                        const created = await createWorkLogAction(clientId, draft)
                        setEntries((prev) => [created, ...prev])
                        setDraft({ ...draft, description: "" })
                      })}>
              Add (publishes immediately)
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 5: Mount it on the activity page**

In `frontend/src/app/clients/[id]/activity/page.tsx`: import `getWorkLog` alongside `getActivityLog`, fetch both in the existing server component (`const workLog = await getWorkLog(id).catch(() => [])`), and render `<WorkLogCard clientId={id} initialEntries={workLog} />` **above** the existing raw activity list.

- [ ] **Step 6: Verify the frontend builds**

Run (from `frontend/`): `npm run typecheck` then `npm run build`
Expected: typecheck clean, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(work-log): admin work-log card on the activity page"
```

---

### Task 6: Monthly report v2 — six new sections

**Files:**
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/prompts/report.py`
- Test: `backend/tests/test_report_v2.py`

**Interfaces:**
- Produces dataclasses in `report_service.py`: `WorkLogLine(category_label, description, entry_date)`; `TechnicalHealth(passed, warned, failed, fixed_checks: list[str])`; `ContentDelivered(titles: list[str], improvements: list[str])`; `AuthorityProgress(newly_live: list[str], newly_verified: list[str], review_deltas: list[str])`; `SourcesTrend(share_now: float, share_then: float | None, flips: list[str])`; `BeforeAfterCard(query_text, platform_label, excerpt)`.
- New `ReportData` fields (all optional, defaulting empty/None): `work_log: list[WorkLogLine]`, `work_log_counts: dict[str, int]`, `technical_health: TechnicalHealth | None`, `content_delivered: ContentDelivered | None`, `authority_progress: AuthorityProgress | None`, `sources_trend: SourcesTrend | None`, `before_after: list[BeforeAfterCard]`.
- Six `_gather_*(client, db, since) -> ...` helpers and six `_build_*_html(data) -> str` builders (each returns `""` when empty).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_report_v2.py`:

```python
"""Report v2 sections (spec §4, §7). Each section renders only with data."""
from datetime import date, timedelta
from unittest.mock import patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _minimal_data(**overrides):
    """A ReportData with only the v1 required fields set."""
    from app.services.report_service import ReportData
    from app.core.time import utcnow
    base = dict(
        period_start=utcnow(), period_end=utcnow(), period_label="July 2026",
        overall_score=70.0, score_band="good", score_color="green",
        ai_citability=70.0, brand_authority=60.0, content_quality=60.0,
        technical_foundations=80.0, structured_data=80.0,
        prev_overall_score=65.0, trend="up", seen_count=7, total_count=10,
        llms_verified=True, schema_verified=True, robots_verified=True,
    )
    base.update(overrides)
    return ReportData(**base)


# 6. A client with nothing new → zero new headers, no error.
def test_no_new_data_renders_no_new_sections():
    from app.services import report_service
    html = report_service._build_report_html(
        type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})(),
        _minimal_data(),
    )
    for header in ("Work Delivered", "Technical Health", "Content Delivered",
                   "Authority Progress", "AI Sources", "Before"):
        assert header not in html


# 5. All sections populated → all six headers present.
def test_all_sections_render_when_populated():
    from app.services import report_service as rs
    data = _minimal_data(
        work_log=[rs.WorkLogLine("Technical", "Verified llms.txt", date(2026, 7, 20))],
        work_log_counts={"technical": 1},
        technical_health=rs.TechnicalHealth(passed=8, warned=1, failed=1,
                                            fixed_checks=["Sitemap reachable"]),
        content_delivered=rs.ContentDelivered(titles=["Dental FAQ pack"],
                                              improvements=["/services: 45 → 78"]),
        authority_progress=rs.AuthorityProgress(newly_live=["LinkedIn"],
                                                newly_verified=["Google Business Profile"],
                                                review_deltas=["Google rating 4.2 → 4.5"]),
        sources_trend=rs.SourcesTrend(share_now=42.0, share_then=31.0,
                                      flips=["cameragear.com"]),
        before_after=[rs.BeforeAfterCard("best dental clinic in KL", "ChatGPT",
                                         "Acme Dental is a leading clinic...")],
    )
    html = rs._build_report_html(
        type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})(),
        data,
    )
    assert "Work Delivered" in html
    assert "Technical Health" in html
    assert "Content Delivered" in html
    assert "Authority Progress" in html
    assert "AI Sources" in html
    assert "Before" in html
    # Language rules: never "cited"
    assert "cited" not in html.lower().replace("seen by ai", "")


# 7. A gather helper raising → section absent, report still builds.
def test_gather_failure_skips_section_not_report(db):
    from app.services import report_service
    client = _make_client(db)
    with patch.object(report_service, "_gather_work_log", side_effect=Exception("boom")):
        data = report_service._gather_report_data(client, db)
    # No scan → None is fine; the point is no exception escaped.
    assert data is None or data.work_log == []


# 8. Period boundary: an entry dated outside the window is excluded.
def test_work_log_gather_respects_period(db):
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    today = utcnow().date()
    inside = work_log_service.suggest(client.id, "technical", "Inside", "r:i", db, entry_date=today)
    work_log_service.update_entry(inside, {"status": "published"}, db)
    outside = work_log_service.suggest(
        client.id, "technical", "Outside", "r:o", db, entry_date=today - timedelta(days=60))
    work_log_service.update_entry(outside, {"status": "published"}, db)

    lines, counts = report_service._gather_work_log(client, db, today - timedelta(days=30))
    descriptions = [line.description for line in lines]
    assert "Inside" in descriptions
    assert "Outside" not in descriptions
    assert counts.get("technical") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_report_v2.py -q`
Expected: FAIL — `AttributeError: module 'app.services.report_service' has no attribute 'WorkLogLine'`.

- [ ] **Step 3: Add the dataclasses and ReportData fields**

In `backend/app/services/report_service.py`, add after the existing `TrendPoint` dataclass (~line 383):

```python
@dataclass
class WorkLogLine:
    category_label: str
    description: str
    entry_date: date


@dataclass
class TechnicalHealth:
    passed: int
    warned: int
    failed: int
    fixed_checks: list[str] = field(default_factory=list)


@dataclass
class ContentDelivered:
    titles: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


@dataclass
class AuthorityProgress:
    newly_live: list[str] = field(default_factory=list)
    newly_verified: list[str] = field(default_factory=list)
    review_deltas: list[str] = field(default_factory=list)


@dataclass
class SourcesTrend:
    share_now: float
    share_then: float | None = None
    flips: list[str] = field(default_factory=list)


@dataclass
class BeforeAfterCard:
    query_text: str
    platform_label: str
    excerpt: str
```

Add `from datetime import date` to the existing datetime import line if not already present.

Append these fields to `ReportData` (after `proof_cards`):

```python
    # ── Report v2 (Phase 5): every field optional; an empty phase yields no section.
    work_log: list["WorkLogLine"] = field(default_factory=list)
    work_log_counts: dict = field(default_factory=dict)
    technical_health: "TechnicalHealth | None" = None
    content_delivered: "ContentDelivered | None" = None
    authority_progress: "AuthorityProgress | None" = None
    sources_trend: "SourcesTrend | None" = None
    before_after: list["BeforeAfterCard"] = field(default_factory=list)
```

- [ ] **Step 4: Add the six gather helpers**

Add above `_gather_report_data` in `report_service.py`:

```python
_MAX_WORK_LOG_LINES = 10
_MAX_BEFORE_AFTER = 3


def _gather_work_log(client: Client, db: Session, since_date) -> tuple[list[WorkLogLine], dict]:
    """Published work-log entries in the period + per-category counts."""
    from app.core.constants import WORK_LOG_CATEGORY_LABELS
    from app.services import work_log_service
    entries = work_log_service.published_entries(client.id, db, since=since_date)
    counts: dict = {}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1
    lines = [
        WorkLogLine(
            category_label=WORK_LOG_CATEGORY_LABELS.get(e.category, e.category.title()),
            description=e.description,
            entry_date=e.entry_date,
        )
        for e in entries[:_MAX_WORK_LOG_LINES]
    ]
    return lines, counts


def _gather_technical_health(client: Client, db: Session, since) -> TechnicalHealth | None:
    """Latest SiteAudit vs the last one before the period (Phase 2)."""
    from app.models.site_audit import SiteAudit
    audits = (
        db.query(SiteAudit)
        .filter(SiteAudit.client_id == client.id)
        .order_by(desc(SiteAudit.created_at))
        .limit(2)
        .all()
    )
    if not audits:
        return None
    latest = audits[0]
    checks = latest.checks or []
    passed = sum(1 for c in checks if c.get("status") == "pass")
    warned = sum(1 for c in checks if c.get("status") == "warn")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    fixed: list[str] = []
    if len(audits) > 1:
        prev_bad = {
            c.get("id") for c in (audits[1].checks or [])
            if c.get("status") in ("warn", "fail")
        }
        fixed = [
            c.get("label") or c.get("id", "")
            for c in checks
            if c.get("status") == "pass" and c.get("id") in prev_bad
        ]
    return TechnicalHealth(passed=passed, warned=warned, failed=failed, fixed_checks=fixed)


def _gather_content_delivered(client: Client, db: Session, since) -> ContentDelivered | None:
    """Reviewed deliverables + page-audit score improvements this period (Phase 3)."""
    from urllib.parse import urlparse

    from app.models.content_deliverable import ContentDeliverable
    from app.models.page_audit import PageAudit
    titles = [
        d.title for d in db.query(ContentDeliverable).filter(
            ContentDeliverable.client_id == client.id,
            ContentDeliverable.status == "reviewed",
            ContentDeliverable.reviewed_at.isnot(None),
            ContentDeliverable.reviewed_at >= since,
        ).all()
    ]
    audits = (
        db.query(PageAudit)
        .filter(PageAudit.client_id == client.id)
        .order_by(desc(PageAudit.created_at))
        .all()
    )
    seen: dict[str, PageAudit] = {}
    improvements: list[str] = []
    for a in audits:
        if a.url in seen:
            older = a
            newer = seen[a.url]
            if newer.created_at >= since and newer.score > older.score:
                path = urlparse(newer.url).path or "/"
                improvements.append(f"{path}: {older.score} → {newer.score}")
            continue
        seen[a.url] = a
    if not titles and not improvements:
        return None
    return ContentDelivered(titles=titles, improvements=improvements)


def _gather_authority_progress(client: Client, db: Session, since) -> AuthorityProgress | None:
    """Assets that went live/verified this period + review-snapshot deltas (Phase 4)."""
    from app.models.authority_asset import AuthorityAsset
    assets = (
        db.query(AuthorityAsset)
        .filter(AuthorityAsset.client_id == client.id, AuthorityAsset.hidden.is_(False))
        .all()
    )
    newly_live = [a.name for a in assets if a.status == "live" and a.updated_at and a.updated_at >= since]
    newly_verified = [
        a.name for a in assets if a.status == "verified" and a.updated_at and a.updated_at >= since
    ]
    deltas: list[str] = []
    for a in assets:
        snaps = a.review_snapshots or []
        if len(snaps) >= 2:
            first, last = snaps[-2], snaps[-1]
            if last.get("rating") != first.get("rating") or last.get("count") != first.get("count"):
                deltas.append(
                    f"{a.name} rating {first.get('rating')} → {last.get('rating')}, "
                    f"{first.get('count')} → {last.get('count')} reviews"
                )
    if not newly_live and not newly_verified and not deltas:
        return None
    return AuthorityProgress(
        newly_live=newly_live, newly_verified=newly_verified, review_deltas=deltas
    )


def _gather_sources_trend(client: Client, db: Session, since) -> SourcesTrend | None:
    """Client share-of-source over the period + flips won (Phase 1)."""
    from app.models.share_of_source_snapshot import ShareOfSourceSnapshot
    snaps = (
        db.query(ShareOfSourceSnapshot)
        .filter(ShareOfSourceSnapshot.client_id == client.id)
        .order_by(desc(ShareOfSourceSnapshot.computed_at))
        .limit(2)
        .all()
    )
    if not snaps:
        return None
    now = snaps[0]
    then = snaps[1] if len(snaps) > 1 else None
    flips: list[str] = []
    if then is not None:
        then_absent = {
            e.get("domain") for e in (then.acquisition_list or []) if e.get("domain")
        }
        now_domains = {
            e.get("domain") for e in (now.acquisition_list or []) if e.get("domain")
        }
        flips = sorted(d for d in then_absent - now_domains if d)[:3]
    return SourcesTrend(
        share_now=now.client_share_pct,
        share_then=then.client_share_pct if then else None,
        flips=flips,
    )


def _gather_before_after(client: Client, db: Session, since) -> list[BeforeAfterCard]:
    """Up to 3 queries that flipped to Seen by AI, with the verbatim snippet now."""
    from app.services import proof_card_service
    from app.services.scan_diff_service import compute_scan_diff
    diff = compute_scan_diff(client.id, db)
    if not diff.newly_seen or not diff.latest_scan_id:
        return []
    competitors = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    wanted = {(q.platform, q.query_text) for q in diff.newly_seen}
    results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == diff.latest_scan_id,
            ScanQueryResult.competitor_id.is_(None),
        )
        .all()
    )
    cards: list[BeforeAfterCard] = []
    for r in results:
        if (r.platform, r.query_text) not in wanted:
            continue
        _, excerpt = proof_card_service.result_excerpt(r, client.name, competitors, redact=False)
        if not excerpt:
            continue
        cards.append(BeforeAfterCard(
            query_text=r.query_text,
            platform_label=PLATFORM_LABELS.get(r.platform, r.platform.title()),
            excerpt=excerpt,
        ))
        if len(cards) >= _MAX_BEFORE_AFTER:
            break
    return cards
```

- [ ] **Step 5: Call the gathers from `_gather_report_data`, each individually guarded**

Immediately before `_gather_report_data`'s `return ReportData(...)`, add:

```python
    # ── Report v2 sections. Each is independently guarded: a failure logs and
    # skips its own section — it must never take the whole report down.
    since_date = since.date()

    def _safe(label: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            logger.warning("report_section_failed", section=label,
                           client_id=str(client.id), error=str(exc))
            return default

    work_log, work_log_counts = _safe(
        "work_log", lambda: _gather_work_log(client, db, since_date), ([], {}))
    technical_health = _safe(
        "technical_health", lambda: _gather_technical_health(client, db, since), None)
    content_delivered = _safe(
        "content_delivered", lambda: _gather_content_delivered(client, db, since), None)
    authority_progress = _safe(
        "authority_progress", lambda: _gather_authority_progress(client, db, since), None)
    sources_trend = _safe(
        "sources_trend", lambda: _gather_sources_trend(client, db, since), None)
    before_after = _safe(
        "before_after", lambda: _gather_before_after(client, db, since), [])
```

and pass them into the `ReportData(...)` constructor:

```python
        work_log=work_log,
        work_log_counts=work_log_counts,
        technical_health=technical_health,
        content_delivered=content_delivered,
        authority_progress=authority_progress,
        sources_trend=sources_trend,
        before_after=before_after,
```

Confirm `logger` exists in this module (structlog); if not, add `logger = structlog.get_logger()` next to the other module-level constants and import structlog.

- [ ] **Step 6: Add the six HTML builders**

Add near the other `_build_*_html` helpers:

```python
def _build_work_log_html(data: ReportData) -> str:
    if not data.work_log:
        return ""
    from app.core.constants import WORK_LOG_CATEGORY_LABELS
    counts = " · ".join(
        f"{WORK_LOG_CATEGORY_LABELS.get(k, k.title())}: {v}"
        for k, v in sorted(data.work_log_counts.items())
    )
    rows = "".join(
        f'<tr><td>{line.entry_date.strftime("%d %b")}</td>'
        f'<td>{html.escape(line.category_label)}</td>'
        f'<td>{html.escape(line.description)}</td></tr>'
        for line in data.work_log
    )
    return (
        f'<h2>Work Delivered This Month</h2>'
        f'<div class="stat-card"><div class="stat-sub">{html.escape(counts)}</div></div>'
        f'<table><thead><tr><th>Date</th><th>Type</th><th>What we did</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


def _build_technical_health_html(data: ReportData) -> str:
    t = data.technical_health
    if t is None:
        return ""
    fixed = ""
    if t.fixed_checks:
        items = "".join(f"<li>{html.escape(c)}</li>" for c in t.fixed_checks)
        fixed = f'<div class="stat-sub">Fixed this period:</div><ul>{items}</ul>'
    return (
        f'<h2>Technical Health</h2>'
        f'<div class="stat-card">'
        f'<div class="stat-sub">{t.passed} checks passing, {t.warned} needing attention, '
        f'{t.failed} failing.</div>{fixed}</div>'
    )


def _build_content_delivered_html(data: ReportData) -> str:
    c = data.content_delivered
    if c is None:
        return ""
    parts = []
    if c.titles:
        items = "".join(f"<li>{html.escape(t)}</li>" for t in c.titles)
        parts.append(f'<div class="stat-sub">Content delivered:</div><ul>{items}</ul>')
    if c.improvements:
        items = "".join(f"<li>{html.escape(i)}</li>" for i in c.improvements)
        parts.append(f'<div class="stat-sub">Pages made easier for AI to read:</div><ul>{items}</ul>')
    return f'<h2>Content Delivered</h2><div class="stat-card">{"".join(parts)}</div>'


def _build_authority_progress_html(data: ReportData) -> str:
    a = data.authority_progress
    if a is None:
        return ""
    parts = []
    if a.newly_verified:
        parts.append(f'<div class="stat-sub">Verified this period: '
                     f'{html.escape(", ".join(a.newly_verified))}</div>')
    if a.newly_live:
        parts.append(f'<div class="stat-sub">Now live: '
                     f'{html.escape(", ".join(a.newly_live))}</div>')
    if a.review_deltas:
        items = "".join(f"<li>{html.escape(d)}</li>" for d in a.review_deltas)
        parts.append(f"<ul>{items}</ul>")
    return f'<h2>Authority Progress</h2><div class="stat-card">{"".join(parts)}</div>'


def _build_sources_trend_html(data: ReportData) -> str:
    s = data.sources_trend
    if s is None:
        return ""
    if s.share_then is None:
        line = (f"Your business appears in {s.share_now:.0f}% of the sources AI answers "
                f"drew from.")
    else:
        line = (f"Your business appears in {s.share_now:.0f}% of the sources AI answers "
                f"drew from, versus {s.share_then:.0f}% previously.")
    flips = ""
    if s.flips:
        items = "".join(f"<li>{html.escape(d)}</li>" for d in s.flips)
        flips = f'<div class="stat-sub">These sources now include you:</div><ul>{items}</ul>'
    return (
        f'<h2>AI Sources Trend</h2>'
        f'<div class="stat-card"><div class="stat-sub">{line}</div>{flips}</div>'
    )


def _build_before_after_html(data: ReportData) -> str:
    if not data.before_after:
        return ""
    cards = "".join(
        f'<div class="stat-card">'
        f'<div class="stat-label">{html.escape(c.query_text)}</div>'
        f'<div class="stat-sub">{html.escape(c.platform_label)} — previously Not seen by AI</div>'
        f'<div class="stat-sub">&ldquo;{html.escape(c.excerpt)}&rdquo;</div>'
        f'</div>'
        for c in data.before_after
    )
    return f'<h2>Before &amp; After</h2>{cards}'
```

- [ ] **Step 7: Wire the sections into `_build_report_html`**

Inside `_build_report_html`, alongside the other section variables, add:

```python
    # ── Report v2 sections (Phase 5) ──────────────────────────────────────
    work_log_section = _build_work_log_html(data)
    technical_health_section = _build_technical_health_html(data)
    content_delivered_section = _build_content_delivered_html(data)
    authority_progress_section = _build_authority_progress_html(data)
    sources_trend_section = _build_sources_trend_html(data)
    before_after_section = _build_before_after_html(data)
```

Then insert those six variables into the returned HTML f-string, in that order, immediately after the existing score/dimension sections and before the report footer. Read the existing f-string body to place them; keep the existing section order intact.

- [ ] **Step 8: Give the narrative the delivered-work counts**

In `backend/app/prompts/report.py`'s `build_change_narrative(data)`, add a context block (counts only, never full text) before the JSON contract:

```python
    delivered = getattr(data, "work_log_counts", None) or {}
    delivered_line = (
        "Work delivered this period (counts by type): "
        + ", ".join(f"{k}: {v}" for k, v in sorted(delivered.items()))
        if delivered else "No delivery records were published for this period."
    )
```

and interpolate `{delivered_line}` into the prompt body so the narrative can reference delivered work. Then check `backend/app/prompts/registry.py` for this prompt's version constant and bump it (e.g. `NARRATIVE_VERSION = "v2"`); if a test pins the old value, update that assertion to the new one — never weaken the test.

- [ ] **Step 9: Run the tests**

Run: `poetry run pytest tests/test_report_v2.py -q`
Expected: 4 passed.

Then the full suite: `poetry run pytest -q` — all pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/report_service.py backend/app/prompts/report.py backend/app/prompts/registry.py backend/tests/test_report_v2.py
git commit -m "feat(report): v2 sections — work delivered, technical, content, authority, sources, before/after"
```

---

### Task 7: Public progress tab + overview line + scorecard line

**Files:**
- Modify: `backend/app/schemas/client_view.py`, `backend/app/api/v1/client_view.py`
- Modify: `backend/app/services/report_service.py` (scorecard line)
- Create: `frontend/src/app/view/[token]/progress/page.tsx`
- Modify: `frontend/src/components/view/ViewTabs.tsx`, `frontend/src/lib/view-api.ts`, `frontend/src/types/index.ts`, `frontend/src/app/view/[token]/page.tsx`
- Modify: `CLAUDE.md` §9
- Test: `backend/tests/test_client_view_work_log.py`

**Interfaces:**
- Produces: `GET /api/v1/view/{token}/work-log` → `list[ClientViewWorkLogItem]` (fields exactly `description`, `category`, `category_label`, `entry_date`); `ClientViewOverview.has_work_log: bool` and `.improvements_last_30d: int`.
- **Naming (spec correction):** the endpoint is `/work-log`, NOT `/progress` — `/progress` already serves the remediation loop and is untouched. The public *page* route stays `/view/[token]/progress`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_client_view_work_log.py`:

```python
"""Public work-log surface (spec §3.5, §7). Mirrors the fixtures used by the
existing client-view tests — open backend/tests/test_api_client_view.py and
reuse its exact token/fixture pattern."""
from datetime import date, timedelta


def _client_with_token(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com", industry="Dental clinic",
               contact_email="hello@acme.com", share_token="tok_" + "a" * 40)
    db.add(c)
    db.commit()
    return c


def test_work_log_exposes_only_published_and_whitelisted_fields(client, db):
    from app.core.time import utcnow
    from app.services import work_log_service
    c = _client_with_token(db)
    published = work_log_service.suggest(c.id, "technical", "Verified llms.txt", "r:1", db,
                                         entry_date=utcnow().date())
    work_log_service.update_entry(published, {"status": "published"}, db)
    work_log_service.suggest(c.id, "content", "Still suggested", "r:2", db)
    dismissed = work_log_service.suggest(c.id, "content", "Dismissed", "r:3", db)
    work_log_service.update_entry(dismissed, {"status": "dismissed"}, db)

    r = client.get(f"/api/v1/view/{c.share_token}/work-log")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert set(body[0]) == {"description", "category", "category_label", "entry_date"}
    assert body[0]["description"] == "Verified llms.txt"


def test_work_log_invalid_token_404(client, db):
    r = client.get("/api/v1/view/not-a-real-token/work-log")
    assert r.status_code == 404


def test_overview_has_work_log_flag_and_count(client, db):
    from app.core.time import utcnow
    from app.services import work_log_service
    c = _client_with_token(db)
    overview = client.get(f"/api/v1/view/{c.share_token}/overview").json()
    assert overview["has_work_log"] is False
    assert overview["improvements_last_30d"] == 0

    e = work_log_service.suggest(c.id, "technical", "Did a thing", "r:x", db,
                                 entry_date=utcnow().date())
    work_log_service.update_entry(e, {"status": "published"}, db)
    overview2 = client.get(f"/api/v1/view/{c.share_token}/overview").json()
    assert overview2["has_work_log"] is True
    assert overview2["improvements_last_30d"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_client_view_work_log.py -q`
Expected: FAIL — 404 on `/work-log`, `KeyError: 'has_work_log'`.

- [ ] **Step 3: Add the public schema**

In `backend/app/schemas/client_view.py`, add near `ClientViewProgressItem`:

```python
class ClientViewWorkLogItem(BaseModel):
    """One published work-log entry, client-safe. Whitelisted fields only —
    never source, status, ids, or internal notes (CLAUDE.md §8-9)."""
    description: str
    category: str
    category_label: str
    entry_date: date
```

Add `from datetime import date` to that module's imports if absent.

Add to `ClientViewOverview` (next to `has_progress`):

```python
    # Whether any work-log entry has been PUBLISHED (drives the Progress tab).
    # Distinct from has_progress, which is the remediation loop.
    has_work_log: bool = False
    # Count of published work-log entries in the last 30 days.
    improvements_last_30d: int = 0
```

- [ ] **Step 4: Add the endpoint and overview fields**

In `backend/app/api/v1/client_view.py`, add the route (place it next to the existing `/progress` route):

```python
@router.get("/work-log", response_model=list[ClientViewWorkLogItem])
def get_work_log(
    client: Client = Depends(require_non_prospect_share_client),
    db: Session = Depends(get_db),
):
    """Published work-log entries — the client-safe delivery timeline.

    Status is filtered in the service query, so a `suggested` or `dismissed`
    row can never reach a client even if the schema changed (spec §3.5).
    """
    from app.core.constants import WORK_LOG_CATEGORY_LABELS
    from app.services import work_log_service
    return [
        ClientViewWorkLogItem(
            description=e.description,
            category=e.category,
            category_label=WORK_LOG_CATEGORY_LABELS.get(e.category, e.category.title()),
            entry_date=e.entry_date,
        )
        for e in work_log_service.published_entries(client.id, db)
    ]
```

Import `ClientViewWorkLogItem` at the top of the module alongside the other client-view schemas.

In `get_overview`, before constructing `ClientViewOverview(...)`, add:

```python
    from datetime import timedelta

    from app.services import work_log_service
    _since_date = (utcnow() - timedelta(days=30)).date()
    improvements_last_30d = work_log_service.published_count_since(client.id, db, _since_date)
    has_work_log = bool(work_log_service.published_entries(client.id, db))
```

and pass `has_work_log=has_work_log, improvements_last_30d=improvements_last_30d` into the response.

- [ ] **Step 5: Run the backend tests**

Run: `poetry run pytest tests/test_client_view_work_log.py -q`
Expected: 3 passed.

- [ ] **Step 6: Add the scorecard line**

In `generate_scorecard_pdf` (`report_service.py:1453`), compute the published count for the last 30 days and render one line when > 0:

```python
    from datetime import timedelta as _td

    from app.services import work_log_service
    try:
        _improvements = work_log_service.published_count_since(
            client.id, db, (utcnow() - _td(days=30)).date()
        )
    except Exception:
        _improvements = 0
    improvements_line = (
        f'<div class="stat-sub">{_improvements} improvements delivered in the last 30 days</div>'
        if _improvements else ""
    )
```

and interpolate `{improvements_line}` into the scorecard HTML under the score. No other scorecard change.

- [ ] **Step 7: Frontend types + view-api**

Append to `frontend/src/types/index.ts`:

```typescript
export interface ClientViewWorkLogItem {
  description: string
  category: WorkLogCategory
  category_label: string
  entry_date: string
}
```

Add `has_work_log: boolean` and `improvements_last_30d: number` to the existing client-view overview interface in `types/index.ts`.

Append to `frontend/src/lib/view-api.ts`, following that file's existing fetch/None-on-404 pattern:

```typescript
export async function getViewWorkLog(token: string): Promise<ClientViewWorkLogItem[]> {
  return viewFetch<ClientViewWorkLogItem[]>(`/api/v1/view/${token}/work-log`) ?? []
}
```

Match the actual helper name and error convention used by the neighbouring functions in that file (e.g. `getViewOverview`) — do not invent one.

- [ ] **Step 8: The public progress page**

`frontend/src/app/view/[token]/progress/page.tsx`:

```typescript
import { getViewWorkLog } from "@/lib/view-api"

export const dynamic = "force-dynamic"

interface Props {
  params: Promise<{ token: string }>
}

function monthLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" })
}

export default async function ProgressPage({ params }: Props) {
  const { token } = await params
  const entries = await getViewWorkLog(token).catch(() => [])

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-6">
        <h2 className="font-display text-lg font-semibold">Progress</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Your delivery timeline will appear here as work is completed.
        </p>
      </div>
    )
  }

  const groups = new Map<string, typeof entries>()
  for (const e of entries) {
    const key = monthLabel(e.entry_date)
    groups.set(key, [...(groups.get(key) ?? []), e])
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Progress</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {entries.length} improvements delivered.
        </p>
      </div>
      {[...groups.entries()].map(([month, items]) => (
        <div key={month} className="rounded-lg border bg-card p-5">
          <h3 className="font-medium">{month}</h3>
          <ul className="mt-3 space-y-3">
            {items.map((e, i) => (
              <li key={`${e.entry_date}-${i}`} className="flex flex-wrap items-start gap-2">
                <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs text-secondary-foreground">
                  {e.category_label}
                </span>
                <span className="flex-1 text-sm">{e.description}</span>
                <span className="text-xs text-muted-foreground">
                  {new Date(e.entry_date).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 9: Conditional tab + overview line**

In `frontend/src/components/view/ViewTabs.tsx`, add a constant and a prop:

```typescript
const PROGRESS_TAB = { segment: "/progress", label: "Progress" } as const
```

Add `showProgress?: boolean` to `Props`, and include it in the non-prospect tab list after `COMPETITORS_TAB`:

```typescript
        ...(showProgress ? [PROGRESS_TAB] : []),
```

In `frontend/src/app/view/[token]/layout.tsx`, pass it through: `showProgress={overview.has_work_log}`.

In `frontend/src/app/view/[token]/page.tsx` (the overview), render one line under the score when `overview.improvements_last_30d > 0`:

```tsx
{overview.improvements_last_30d > 0 && (
  <a href={`/view/${token}/progress`} className="text-sm text-primary underline-offset-4 hover:underline">
    {overview.improvements_last_30d} improvements delivered in the last 30 days
  </a>
)}
```

- [ ] **Step 10: CLAUDE.md §9**

In `CLAUDE.md` §9's public read-only client view list, add after the `/view/[token]/reports` line:

```
/view/[token]/progress    → delivery timeline (published work log only)
```

- [ ] **Step 11: Verify**

Backend: `poetry run pytest -q` — all pass; `poetry run ruff check app/ tests/` — clean.
Frontend (from `frontend/`): `npm run typecheck` then `npm run build` — clean, with `/view/[token]/progress` in the route list.

- [ ] **Step 12: Commit**

```bash
git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/app/services/report_service.py backend/tests/test_client_view_work_log.py frontend/src CLAUDE.md
git commit -m "feat(work-log): public progress tab + overview line + scorecard line"
```

---

### Task 8: Definition-of-done gate + end-to-end walkthrough

**Files:** none (verification only).

- [ ] **Step 1: Run the seenby-verify gate**

Invoke the `seenby-verify` skill and run everything it specifies:
- `poetry run pytest -q` (from `backend/`) — all green.
- `poetry run ruff check app/ tests/` — "All checks passed!"
- `npm run typecheck && npm run build` (from `frontend/`) — clean.
- `poetry run alembic heads` — exactly one head (the new revision).
- Banned-language scan across every file this phase touched, with special attention to the six new report sections and the work-log templates:

```bash
git diff --name-only master...HEAD | grep -E "\.(py|ts|tsx)$" | while read f; do [ -f "$f" ] && grep -Hni -E "\b(cited|uncited|mentioned)\b|citation rate|ranking position|visibility gap|confidence score|char offset|token count|first mentioned" "$f"; done
```
Expected: no hits outside legitimate negative instructions in prompt files.

- [ ] **Step 2: Confirm the migration is release-ready (do NOT apply)**

`.env` points at prod — the migration runs at release via `seenby-release`, never in development. Confirm the new migration file is **tracked** (`git ls-files backend/alembic/versions/ | grep <revision>`) — an untracked migration is invisible to both `alembic heads` and the SQLite suite, and broke a fresh checkout in Phase 1.

- [ ] **Step 3: End-to-end walkthrough (browser, admin login required)**

With the app running (`run-app` skill), logged in as admin, on a client that has scan history:
1. Trigger something that fires a hook (verify a toolkit file, or set an authority asset to live). Open `/clients/[id]/activity` — the suggestion appears in the **Suggested** queue, not the published timeline.
2. Edit its wording, click **Publish**. It moves to **Published**.
3. Add a manual entry — confirm it lands directly in **Published**.
4. Dismiss a suggestion — confirm it disappears from both client-facing surfaces.
5. Open the client's share link `/view/<token>` — confirm the "N improvements delivered in the last 30 days" line appears and links to the **Progress** tab, and that the tab only lists the **published** entry (never the suggested or dismissed ones).
6. Generate a monthly report PDF for that client and confirm: the new sections appear only where data exists, no empty headers, and the narrative references delivered work.
7. Run `seenby-demo-check` against the client view to confirm no internal fields leaked.

- [ ] **Step 4: Update project memory**

Update `seenby-geo-endtoend-roadmap.md`: mark Phase 5 complete with the merge commit and prod-migration status. **All five phases of the GEO end-to-end roadmap are then done** — note what remains operationally (prod migration, live walkthroughs) and that the roadmap itself is complete.

- [ ] **Step 5: Finish the branch**

Invoke `superpowers:finishing-a-development-branch` and follow the user's choice.

---

## Self-Review

**Spec coverage:**
- §3.1 why not filter ActivityLog → Global Constraints + model docstring state the rule explicitly. ✓
- §3.2 model (all 10 columns, RLS, partial-unique on source_ref, published-only client visibility) → Task 1. ✓
- §3.3 seven auto-suggest triggers with client-safe templates, sanitizer at write, best-effort/no-rollback → Task 3 (source-ref table gives the exact dedupe key + template per trigger). ✓
- §3.3 manual entries created directly as `published` → Task 2 `create_manual` + Task 4 POST. ✓
- §3.4 three admin routes + admin surface on the activity page (suggested queue above published timeline, add form, no new nav page) → Tasks 4 and 5. ✓
- §3.5 public tab, month grouping, category chips, header stat, whitelisted schema, query-level status filter, tab hidden when empty, non-404 empty state → Task 7. ✓
- §4 six report sections, render-only-with-data, per-section failure isolation, narrative context, `ReportData` optional-field shape → Task 6. ✓
- §5 overview line + scorecard line → Task 7 (Steps 6, 9). ✓
- §6 error handling (section skip, best-effort suggest, empty progress tab, whitelisted schemas) → Tasks 2, 6, 7. ✓
- §7 testing: idempotence + no-regression-after-review (Task 2 test 2), sanitizer (test 3), no-rollback (Task 3 test 1), manual published (test 4), transitions (test 5), edit-before-publish (test 6), all-sections/v1-identical/gather-failure/period-boundary (Task 6), public whitelist + uniform 404 + overview line (Task 7). ✓
- §8 build order → Tasks 1–8 follow it (migration → service → hooks → API → admin UI → report → client view → verify). Split §8.2 into service (Task 2) and hooks (Task 3) so each gets its own reviewer gate. ✓

**Placeholder scan:** No TBD/TODO/"handle errors appropriately"/"similar to Task N". Three places deliberately instruct the implementer to *read* neighbouring code rather than guess — the toolkit handler's per-file variable (4c), the site-audit fixed-count delta (4d), and the `view-api.ts` fetch helper name — each states exactly what to look for and forbids inventing names. That is a grounding instruction, not a placeholder.

**Type consistency:** `suggest(client_id, category, description, source_ref, db, entry_date=None)` — signature identical in Task 2's definition and all seven Task 3 call sites. `published_entries(client_id, db, since=None, until=None)` used by Task 6 (`since=since_date`, a `date`) and Task 7 (no window) — `entry_date` is a `Date` column, and Task 6 passes `since.date()`, so the comparison is date-to-date throughout. `published_count_since(client_id, db, since: date)` — Task 7 passes `(utcnow() - timedelta(days=30)).date()`. ✓ `WorkLogEntryOut.category_label` is set post-`model_validate`, so Step 4 of Task 4 explicitly gives it a `""` default. Report dataclass names (`WorkLogLine`, `TechnicalHealth`, `ContentDelivered`, `AuthorityProgress`, `SourcesTrend`, `BeforeAfterCard`) are identical in the Task 6 definitions, the `ReportData` fields, the gather returns, the HTML builders, and the tests. Frontend `WorkLogEntry`/`WorkLogCategory`/`WorkLogStatus` (Task 5) and `ClientViewWorkLogItem` (Task 7) are distinct types for distinct surfaces — deliberate, since the public one carries only four whitelisted fields.

**Two risks flagged for the implementer rather than guessed at:** `_gather_technical_health` assumes `SiteAudit.checks` rows carry `id`/`status`/`label` keys, and `_gather_authority_progress` uses `AuthorityAsset.updated_at` as the period marker (it is `onupdate=utcnow`, so a later unrelated edit re-dates an asset). Both are correct against the models as built in Phases 2 and 4, but the reviewer should confirm the `SiteAudit.checks` key names against that model, and note that the `updated_at` proxy is an approximation the spec's "became live/verified this period" wording tolerates.
