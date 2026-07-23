# Authority & Presence Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each client a tracked, verifiable authority-building checklist (directories, reviews, social, knowledge-graph, NAP) that the admin picks from a master catalog, prioritised by SeenBy's own Share-of-Source provenance data — *"AI answers in your industry drew from these domains; you're absent from N of them."*

**Architecture:** A new `authority_assets` table holds per-client checklist rows created only when the admin explicitly picks them (no auto-seeding). A new `authority_service` owns the catalog picker, CRUD, a URL verification crawler (reusing the existing SSRF-guarded `safe_get`), best-effort NAP extraction, review-snapshot history, and provenance-driven "suggested next" priorities aggregated from `scan_query_sources`. The Brand Authority assessment prompt gains a structured evidence block from these assets. A new admin page `/clients/[id]/authority` renders it all; the client view (`/view/*`) gets nothing this phase.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic, BeautifulSoup via `url_safety.safe_get`, Next.js 15 + shadcn/ui. No new Claude call is added (the only LLM change is a context block bolted onto the existing Brand Authority assessment prompt).

**Spec:** `docs/superpowers/specs/2026-07-11-authority-presence-tracker-design.md`

## Global Constraints

- **No score/dimension change; no SCORE_VERSION bump.** Authority assets feed *evidence* into the existing assisted Brand Authority flow — the admin still gates the number. Nothing here writes a GeoScore or a dimension score.
- **Language rules (CLAUDE.md §2)** on every client-facing string and every stored note: "seen by AI" / "Not seen by AI", never "cited/mentioned"; "visibility frequency", never "citation rate". The provenance rail says "sources AI answers drew from", never "cited". Never surface confidence scores, char offsets, or token counts.
- **No third-party APIs** (Google Reviews / LinkedIn / Trustpilot are gated). Review counts/ratings are admin-entered snapshots; presence is admin status + best-effort single-page reads only.
- **No automated submission or posting.** SeenBy tracks and verifies; Faris does the work. Nothing auto-creates asset rows for a client — the page can legitimately be empty until the admin picks from the catalog.
- **URL crawling is SSRF-guarded and single-page:** every fetch goes through `is_safe_crawl_url` + `safe_get` (10s timeout, 5 MB cap, per-hop re-check). One URL per verify — no crawling beyond it. A failed/blocked/non-200 check never auto-downgrades a status; it only sets `last_checked_at` and returns a human note.
- **Admin-only** (bearer `require_api_key`) on every new route. Client view gets nothing this phase.
- **RLS enabled inline** in the migration for the new table. Current single alembic head is `53304d0628ae` — the new migration's `down_revision`.
- **CLAUDE.md §9 gets the `/authority` line in the same branch** (rule: don't add pages without updating it).
- Frontend: shadcn/ui only; all fetches via `src/lib/api.ts`; types in `src/types/index.ts`. Never hardcode score bands/colors.
- Backend commands (this machine): poetry at `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe`, run from `backend/`. ⚠️ `backend/.env` DATABASE_URL points at PROD Supabase — **never** run `alembic upgrade`/`current` during development; prod migration happens at release via `seenby-release`. `alembic revision`, `alembic heads`, and the SQLite test suite are safe (they touch no prod data).

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/authority_asset.py` (new) | AuthorityAsset row: checklist item, status, url, review snapshots, NAP, provenance_domain, hidden |
| `backend/app/models/client.py` (modify) | + `phone` column (canonical NAP) |
| `backend/alembic/versions/<generated>_add_authority_assets_and_client_phone.py` (new) | authority_assets table (RLS on) + partial-unique (client_id, asset_key) + clients.phone |
| `backend/tests/conftest.py` (modify) | add `authority_asset` to model import list |
| `backend/app/core/constants.py` (modify) | `AUTHORITY_ASSET_TYPES`, `AUTHORITY_ASSET_STATUSES`, `AUTHORITY_ASSET_CATALOG` |
| `backend/app/services/authority_service.py` (new) | catalog, CRUD, verify+NAP, review snapshots, provenance aggregation, suggested-next, assessment summary |
| `backend/app/schemas/authority.py` (new) | request/response schemas |
| `backend/app/api/v1/authority.py` (new) + `router.py` (modify) | 6 admin routes |
| `backend/app/prompts/assessment.py` (modify) | Brand Authority prompt gains authority evidence block; `BRAND_AUTHORITY_VERSION` → `v3` |
| `backend/app/services/assessment_service.py` (modify) | compute + pass authority summary for the brand_authority dimension |
| `frontend/src/app/clients/[id]/authority/` (new) | page.tsx + AuthorityClient.tsx + CatalogPicker.tsx + actions.ts |
| `frontend/src/lib/api.ts`, `src/types/index.ts` (modify) | authority API functions + types |
| `frontend/src/components/layout/Sidebar.tsx` (modify) | nav entry |
| `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` + `actions.ts` (modify) | client phone field |
| `CLAUDE.md` §9 (modify) | `/authority` route line |

---

### Task 1: AuthorityAsset model + client.phone + migration

**Files:**
- Create: `backend/app/models/authority_asset.py`
- Modify: `backend/app/models/client.py` (add `phone`)
- Modify: `backend/tests/conftest.py` (model import list)
- Create: `backend/alembic/versions/<generated>_add_authority_assets_and_client_phone.py`
- Test: `backend/tests/test_authority_models.py`

**Interfaces:**
- Produces: `AuthorityAsset(id, client_id, asset_key: str|None, name, asset_type, url: str|None, status="missing", notes: str|None, provenance_domain: str|None, review_snapshots: list, found_nap: dict|None, nap_mismatch=False, hidden=False, last_checked_at: datetime|None, created_at, updated_at)`; `Client.phone: str|None`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_authority_models.py`:

```python
"""AuthorityAsset + Client.phone persistence (spec §3)."""


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com",
               phone="+60 3-1234 5678")
    db.add(c)
    db.commit()
    return c


def test_client_phone_round_trip(db):
    from app.models.client import Client
    client = _make_client(db)
    assert db.query(Client).one().phone == "+60 3-1234 5678"


def test_authority_asset_defaults(db):
    from app.models.authority_asset import AuthorityAsset
    client = _make_client(db)
    a = AuthorityAsset(
        client_id=client.id, asset_key="gbp", name="Google Business Profile",
        asset_type="review_platform", provenance_domain="google.com",
    )
    db.add(a)
    db.commit()
    row = db.query(AuthorityAsset).one()
    assert row.status == "missing"
    assert row.hidden is False
    assert row.nap_mismatch is False
    assert row.review_snapshots == []
    assert row.found_nap is None
    assert row.url is None
    assert row.last_checked_at is None
    assert row.created_at is not None


def test_authority_asset_custom_has_null_key(db):
    from app.models.authority_asset import AuthorityAsset
    client = _make_client(db)
    a = AuthorityAsset(client_id=client.id, asset_key=None,
                       name="Some niche directory", asset_type="directory")
    db.add(a)
    db.commit()
    assert db.query(AuthorityAsset).one().asset_key is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `poetry run pytest tests/test_authority_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.authority_asset'` (and, after that resolves, an `AttributeError` on `phone` until Step 3b).

- [ ] **Step 3a: Create the model**

`backend/app/models/authority_asset.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class AuthorityAsset(Base):
    """One authority-building checklist item for one client.

    Created ONLY when the admin picks it from AUTHORITY_ASSET_CATALOG (or adds
    a fully custom one) — never auto-seeded (spec §4: Faris's clients span
    industries; a one-size list would be noise). asset_key is the stable
    catalog key ("gbp", "crunchbase") or NULL for custom assets. Archiving is
    soft (`hidden=True`) so history survives for the Phase 5 work log. See
    docs/superpowers/specs/2026-07-11-authority-presence-tracker-design.md.
    """

    __tablename__ = "authority_assets"
    __table_args__ = (
        # One catalog key per client; custom assets (NULL key) are unconstrained.
        Index(
            "uq_authority_assets_client_key", "client_id", "asset_key", unique=True,
            postgresql_where=text("asset_key IS NOT NULL"),
            sqlite_where=text("asset_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # directory | review_platform | social | knowledge_graph | media | other
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # missing | in_progress | live | verified
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="missing", server_default="missing")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # admin-only
    # Domain to match against scan_query_source rows for provenance counts.
    provenance_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # review_platform only: [{"date","rating","count"}], oldest → newest.
    review_snapshots: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # {"name","phone","address_text"} extracted at verify time; NULL until verified.
    found_nap: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    nap_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
```

- [ ] **Step 3b: Add `phone` to the Client model**

In `backend/app/models/client.py`, immediately after the `contact_email` column (line 23), add:

```python
    # Canonical business phone for NAP-consistency checks (spec §3). Admin-entered
    # in settings; compared digits-only against phones found on verified directory pages.
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 3c: Register the model in conftest**

In `backend/tests/conftest.py`, append `, authority_asset` to the end of the model import list (the long `from app.models import ...  # noqa: F401` line), immediately before the `  # noqa: F401`:

```python
... share_of_source_snapshot, control_query, guarantee, site_audit, page_audit, content_deliverable, authority_asset  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_authority_models.py -q`
Expected: 3 passed.

- [ ] **Step 5: Create the migration**

Run: `poetry run alembic revision -m "add authority assets and client phone"` (from `backend/`; this does not apply anything). Keep the generated revision ID; replace the file body with (substituting `<generated>`):

```python
"""add authority assets and client phone

Revision ID: <generated>
Revises: 53304d0628ae
Create Date: <keep generated date>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '<generated>'
down_revision: Union[str, None] = '53304d0628ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("phone", sa.String(length=64), nullable=True))

    op.create_table(
        "authority_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("asset_key", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="missing"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("provenance_domain", sa.String(length=255), nullable=True),
        sa.Column("review_snapshots", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("found_nap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("nap_mismatch", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authority_assets_client_id", "authority_assets", ["client_id"])
    op.create_index(
        "uq_authority_assets_client_key", "authority_assets", ["client_id", "asset_key"],
        unique=True, postgresql_where=sa.text("asset_key IS NOT NULL"),
    )
    op.execute("ALTER TABLE authority_assets ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE authority_assets DISABLE ROW LEVEL SECURITY;")
    op.drop_index("uq_authority_assets_client_key", table_name="authority_assets")
    op.drop_index("ix_authority_assets_client_id", table_name="authority_assets")
    op.drop_table("authority_assets")
    op.drop_column("clients", "phone")
```

- [ ] **Step 6: Verify the migration chain (seenby-migrations gate)**

```bash
poetry run alembic heads
```
Expected: exactly ONE head — the new revision ID.

```bash
grep -rn "^revision" alembic/versions/ | sort | uniq -d -f1
```
Expected: no output (no duplicate revision IDs). **Do NOT run `alembic upgrade`** — `.env` points at prod.

- [ ] **Step 7: Run the full backend suite**

Run: `poetry run pytest -q`
Expected: all pass (722+ from Phase 3 baseline, plus the 3 new).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/authority_asset.py backend/app/models/client.py backend/tests/conftest.py backend/tests/test_authority_models.py backend/alembic/versions/
git commit -m "feat(authority): AuthorityAsset model + client.phone + migration"
```

---

### Task 2: Catalog constants + authority_service CRUD

**Files:**
- Modify: `backend/app/core/constants.py` (append)
- Create: `backend/app/services/authority_service.py`
- Test: `backend/tests/test_authority_service.py`

**Interfaces:**
- Produces:
  - `get_catalog(client: Client, db: Session) -> list[dict]` — every catalog item as `{"key","name","type","provenance_domain","url_hint","suggested_industries","added": bool}`, sorted by industry match (matching items first) then by type order.
  - `add_assets(client: Client, items: list[dict], db: Session) -> list[AuthorityAsset]` — each item is `{"asset_key": "<catalog key>"}` (copies catalog fields) OR `{"name","asset_type", optional "url","provenance_domain"}` (custom, `asset_key=None`). Adding an already-present catalog key is a no-op (idempotent). Returns the rows that now exist for the submitted items.
  - `update_asset(asset: AuthorityAsset, patch: dict, db: Session) -> AuthorityAsset` — applies any of `status`, `url`, `notes`, `hidden`; writes an `authority_status_changed` ActivityLog when `status` actually changes.
  - `list_assets(client_id: uuid.UUID, db: Session, include_hidden: bool = False) -> list[AuthorityAsset]` — ordered by asset_type (catalog order) then created_at.
  - `CATALOG_BY_KEY: dict[str, dict]` — catalog indexed by key.
- Consumes: `AUTHORITY_ASSET_CATALOG`, `AUTHORITY_ASSET_TYPES` from constants; `AuthorityAsset`, `Client`, `ActivityLog` models.

- [ ] **Step 1: Add the catalog constants**

Append to `backend/app/core/constants.py`:

```python
# --- Authority & Presence Tracker (Phase 4) ---------------------------------
# Asset types in display order (also the group order on the /authority page).
AUTHORITY_ASSET_TYPES: Final = (
    "directory", "review_platform", "social", "knowledge_graph", "media", "other",
)
# Lifecycle: admin drives missing → in_progress → live; the verify crawler
# attempts live → verified. A failed check never downgrades.
AUTHORITY_ASSET_STATUSES: Final = ("missing", "in_progress", "live", "verified")

# Master reference list the admin picks from per client — NOT auto-seeded
# (spec §4). suggested_industries only SORTS the picker; it never auto-selects.
# Malaysia-first starting menu; trim/extend per client freely.
AUTHORITY_ASSET_CATALOG: Final = [
    {"key": "gbp", "name": "Google Business Profile", "type": "review_platform",
     "provenance_domain": "google.com", "url_hint": "https://business.google.com/",
     "suggested_industries": []},
    {"key": "trustpilot", "name": "Trustpilot", "type": "review_platform",
     "provenance_domain": "trustpilot.com", "url_hint": "https://www.trustpilot.com/",
     "suggested_industries": []},
    {"key": "facebook_reviews", "name": "Facebook Page reviews", "type": "review_platform",
     "provenance_domain": "facebook.com", "url_hint": "https://www.facebook.com/",
     "suggested_industries": []},
    {"key": "crunchbase", "name": "Crunchbase", "type": "directory",
     "provenance_domain": "crunchbase.com", "url_hint": "https://www.crunchbase.com/",
     "suggested_industries": ["saas", "tech", "startup"]},
    {"key": "clutch", "name": "Clutch", "type": "directory",
     "provenance_domain": "clutch.co", "url_hint": "https://clutch.co/",
     "suggested_industries": ["agency", "services", "software"]},
    {"key": "yellowpages_my", "name": "Yellow Pages Malaysia", "type": "directory",
     "provenance_domain": "yellowpages.my", "url_hint": "https://www.yellowpages.my/",
     "suggested_industries": []},
    {"key": "smecorp", "name": "SME Corp Malaysia directory", "type": "directory",
     "provenance_domain": "smecorp.gov.my", "url_hint": "https://www.smecorp.gov.my/",
     "suggested_industries": ["sme", "retail", "manufacturing"]},
    {"key": "foursquare", "name": "Foursquare / Apple Maps listing", "type": "directory",
     "provenance_domain": "foursquare.com", "url_hint": "https://foursquare.com/",
     "suggested_industries": ["retail", "restaurant", "clinic"]},
    {"key": "myhealth_clinic", "name": "MyHEALTH / MMC clinic directory", "type": "directory",
     "provenance_domain": "myhealth.gov.my", "url_hint": "http://www.myhealth.gov.my/",
     "suggested_industries": ["healthcare", "clinic", "dental"]},
    {"key": "linkedin", "name": "LinkedIn company page", "type": "social",
     "provenance_domain": "linkedin.com", "url_hint": "https://www.linkedin.com/company/",
     "suggested_industries": []},
    {"key": "youtube", "name": "YouTube channel", "type": "social",
     "provenance_domain": "youtube.com", "url_hint": "https://www.youtube.com/",
     "suggested_industries": []},
    {"key": "facebook", "name": "Facebook page", "type": "social",
     "provenance_domain": "facebook.com", "url_hint": "https://www.facebook.com/",
     "suggested_industries": []},
    {"key": "instagram", "name": "Instagram profile", "type": "social",
     "provenance_domain": "instagram.com", "url_hint": "https://www.instagram.com/",
     "suggested_industries": ["retail", "restaurant", "beauty", "clinic"]},
    {"key": "wikidata", "name": "Wikidata entity", "type": "knowledge_graph",
     "provenance_domain": "wikidata.org", "url_hint": "https://www.wikidata.org/",
     "suggested_industries": []},
    {"key": "wikipedia_readiness", "name": "Wikipedia readiness (checklist only)",
     "type": "knowledge_graph", "provenance_domain": "wikipedia.org",
     "url_hint": "https://en.wikipedia.org/", "suggested_industries": []},
    {"key": "schema_sameas", "name": "sameAs links in site schema",
     "type": "knowledge_graph", "provenance_domain": None, "url_hint": None,
     "suggested_industries": []},
    {"key": "media_mention", "name": "Industry blog / news mention target",
     "type": "media", "provenance_domain": None, "url_hint": None,
     "suggested_industries": []},
]
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_authority_service.py`:

```python
"""authority_service — catalog, CRUD (spec §4, §10). Real db fixture."""


def _make_client(db, industry="Dental clinic"):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry=industry, contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_catalog_lists_all_items_unadded_for_new_client(db):
    from app.services import authority_service
    client = _make_client(db)
    catalog = authority_service.get_catalog(client, db)
    from app.core.constants import AUTHORITY_ASSET_CATALOG
    assert len(catalog) == len(AUTHORITY_ASSET_CATALOG)
    assert all(item["added"] is False for item in catalog)


def test_catalog_sorts_industry_matches_first(db):
    from app.services import authority_service
    client = _make_client(db, industry="Healthcare / dental clinic")
    catalog = authority_service.get_catalog(client, db)
    # myhealth_clinic (suggested_industries includes "dental"/"clinic") sorts
    # ahead of an item with no industry hint.
    keys = [i["key"] for i in catalog]
    assert keys.index("myhealth_clinic") < keys.index("linkedin")


def test_add_selected_catalog_keys_creates_exactly_those(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}, {"asset_key": "linkedin"}], db)
    rows = db.query(AuthorityAsset).filter(AuthorityAsset.client_id == client.id).all()
    assert {r.asset_key for r in rows} == {"gbp", "linkedin"}
    gbp = next(r for r in rows if r.asset_key == "gbp")
    assert gbp.name == "Google Business Profile"
    assert gbp.asset_type == "review_platform"
    assert gbp.provenance_domain == "google.com"
    assert gbp.status == "missing"


def test_add_is_idempotent_on_catalog_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    assert db.query(AuthorityAsset).filter(
        AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key == "gbp"
    ).count() == 1


def test_add_custom_asset_has_null_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    rows = authority_service.add_assets(
        client,
        [{"name": "Klinik directory XYZ", "asset_type": "directory",
          "url": "https://xyz.example/acme", "provenance_domain": "xyz.example"}],
        db,
    )
    assert len(rows) == 1
    row = db.query(AuthorityAsset).one()
    assert row.asset_key is None
    assert row.name == "Klinik directory XYZ"
    assert row.provenance_domain == "xyz.example"


def test_update_status_writes_activity_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "in_progress"}, db)
    log = db.query(ActivityLog).filter(
        ActivityLog.client_id == client.id,
        ActivityLog.event_type == "authority_status_changed",
    ).one()
    assert "in progress" in log.note.lower()
    assert asset.status == "in_progress"


def test_update_same_status_writes_no_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"url": "https://g.co/acme"}, db)  # no status change
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed"
    ).count() == 0
    assert asset.url == "https://g.co/acme"


def test_hidden_assets_excluded_by_default(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"hidden": True}, db)
    assert authority_service.list_assets(client.id, db) == []
    assert len(authority_service.list_assets(client.id, db, include_hidden=True)) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.authority_service'`

- [ ] **Step 4: Implement the service (CRUD half)**

`backend/app/services/authority_service.py`:

```python
"""Authority & Presence Tracker — per-client authority checklist (spec §4-§10).

Nothing is auto-created for a client: rows exist only after the admin picks
from AUTHORITY_ASSET_CATALOG or adds a custom asset. Verification is a single
SSRF-guarded page read (Task 3); provenance-driven priorities read
scan_query_sources (Task 4). No score is written here — assets feed evidence
into the assisted Brand Authority flow, admin still gates the number.
"""
import uuid

import structlog
from sqlalchemy.orm import Session

from app.core.constants import AUTHORITY_ASSET_CATALOG, AUTHORITY_ASSET_TYPES
from app.models.activity_log import ActivityLog
from app.models.authority_asset import AuthorityAsset
from app.models.client import Client

logger = structlog.get_logger()

CATALOG_BY_KEY: dict[str, dict] = {item["key"]: item for item in AUTHORITY_ASSET_CATALOG}
_TYPE_ORDER = {t: i for i, t in enumerate(AUTHORITY_ASSET_TYPES)}
_STATUS_LABELS = {
    "missing": "missing", "in_progress": "in progress",
    "live": "live", "verified": "verified",
}


def _industry_match(item: dict, industry: str) -> bool:
    """True when any of the item's suggested_industries appears in the client's
    industry text (case-insensitive substring) — a soft SORT hint only."""
    low = (industry or "").lower()
    return any(hint.lower() in low for hint in item.get("suggested_industries", []))


def get_catalog(client: Client, db: Session) -> list[dict]:
    """Full master catalog with an `added` flag per item, industry-sorted.

    Matching-industry items float to the top; ties keep the catalog's type
    order. Never auto-selects — the flag just tells the picker what to disable.
    """
    added_keys = {
        r.asset_key
        for r in db.query(AuthorityAsset.asset_key)
        .filter(AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key.isnot(None))
        .all()
    }
    items = [
        {
            "key": item["key"], "name": item["name"], "type": item["type"],
            "provenance_domain": item["provenance_domain"], "url_hint": item["url_hint"],
            "suggested_industries": item["suggested_industries"],
            "added": item["key"] in added_keys,
        }
        for item in AUTHORITY_ASSET_CATALOG
    ]
    items.sort(key=lambda i: (
        0 if _industry_match(i, client.industry) else 1,
        _TYPE_ORDER.get(i["type"], 99),
    ))
    return items


def list_assets(
    client_id: uuid.UUID, db: Session, include_hidden: bool = False
) -> list[AuthorityAsset]:
    """Client's assets, ordered by type (catalog order) then created_at."""
    q = db.query(AuthorityAsset).filter(AuthorityAsset.client_id == client_id)
    if not include_hidden:
        q = q.filter(AuthorityAsset.hidden.is_(False))
    rows = q.all()
    rows.sort(key=lambda a: (_TYPE_ORDER.get(a.asset_type, 99), a.created_at))
    return rows


def add_assets(client: Client, items: list[dict], db: Session) -> list[AuthorityAsset]:
    """Add catalog and/or custom assets. Catalog keys are idempotent (upsert).

    - {"asset_key": "<key>"}  → copy catalog name/type/provenance_domain; skip
      if the client already has that key.
    - {"name","asset_type", optional "url","provenance_domain"} → custom row.
    Returns the AuthorityAsset rows corresponding to the submitted items
    (existing row for an already-present key; the new row otherwise).
    """
    existing = {
        r.asset_key: r
        for r in db.query(AuthorityAsset)
        .filter(AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key.isnot(None))
        .all()
    }
    result: list[AuthorityAsset] = []
    to_add: list[AuthorityAsset] = []
    for item in items:
        key = item.get("asset_key")
        if key:
            if key in existing:
                result.append(existing[key])
                continue
            cat = CATALOG_BY_KEY.get(key)
            if cat is None:
                continue  # unknown key — ignore rather than 500
            row = AuthorityAsset(
                client_id=client.id, asset_key=key, name=cat["name"],
                asset_type=cat["type"], provenance_domain=cat["provenance_domain"],
                url=item.get("url") or None,
            )
        else:
            name = (item.get("name") or "").strip()
            asset_type = item.get("asset_type") or "other"
            if not name or asset_type not in AUTHORITY_ASSET_TYPES:
                continue
            row = AuthorityAsset(
                client_id=client.id, asset_key=None, name=name, asset_type=asset_type,
                url=item.get("url") or None,
                provenance_domain=(item.get("provenance_domain") or None),
            )
        to_add.append(row)
        existing[key] = row if key else existing.get(key)  # dedupe within one call
        result.append(row)

    if to_add:
        db.add_all(to_add)
        db.add(ActivityLog(
            client_id=client.id, event_type="authority_assets_added",
            note=f"Added {len(to_add)} authority asset(s) to the checklist.",
        ))
        db.commit()
        for row in to_add:
            db.refresh(row)
    return result


def update_asset(asset: AuthorityAsset, patch: dict, db: Session) -> AuthorityAsset:
    """Apply status/url/notes/hidden. Logs only when status actually changes."""
    status_changed = False
    if "status" in patch and patch["status"] and patch["status"] != asset.status:
        asset.status = patch["status"]
        status_changed = True
    if "url" in patch:
        asset.url = patch["url"] or None
    if "notes" in patch:
        asset.notes = patch["notes"] or None
    if "hidden" in patch and patch["hidden"] is not None:
        asset.hidden = bool(patch["hidden"])

    if status_changed:
        db.add(ActivityLog(
            client_id=asset.client_id, event_type="authority_status_changed",
            note=f"{asset.name} moved to {_STATUS_LABELS.get(asset.status, asset.status)}.",
        ))
    db.commit()
    db.refresh(asset)
    return asset
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/constants.py backend/app/services/authority_service.py backend/tests/test_authority_service.py
git commit -m "feat(authority): catalog constants + asset CRUD service"
```

---

### Task 3: Verify crawler + NAP extraction + review snapshots

**Files:**
- Modify: `backend/app/services/authority_service.py` (append)
- Test: `backend/tests/test_authority_service.py` (append)

**Interfaces:**
- Produces:
  - `verify_asset(asset: AuthorityAsset, client: Client, db: Session) -> tuple[AuthorityAsset, str]` — fetches `asset.url` once; on the client name being present, sets `status="verified"` (from any status) + logs; extracts NAP; sets `nap_mismatch`; always sets `last_checked_at`. Returns `(asset, human_note)`. Never raises on a fetch failure.
  - `add_review_snapshot(asset: AuthorityAsset, rating: float, count: int, db: Session) -> AuthorityAsset` — appends `{"date","rating","count"}` (today, ISO date) to `review_snapshots`; logs `review_snapshot_added`.
  - `extract_nap(page_text: str, client: Client) -> dict` — `{"name","phone","address_text"}`, best-effort (values may be None).
- Consumes: `is_safe_crawl_url`, `safe_get` from `url_safety`; `detect_brand_mention` from `brand_detection`; `utcnow` from `app.core.time`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_authority_service.py`:

```python
from unittest.mock import patch

from app.services.url_safety import SafeResponse

_PAGE_WITH_NAME = (
    "<html><body><h1>Acme Dental Clinic</h1>"
    "<p>Call us at +60 3-1234 5678. 12 Jalan Ampang, Kuala Lumpur.</p>"
    "</body></html>"
)
_PAGE_WITHOUT_NAME = "<html><body><p>Some unrelated directory listing.</p></body></html>"
_PAGE_WRONG_PHONE = (
    "<html><body><h1>Acme Dental Clinic</h1>"
    "<p>Phone: 03-9999 0000</p></body></html>"
)


def _ok(html):
    return SafeResponse(200, html, {"content-type": "text/html"})


def test_verify_marks_verified_when_name_present(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITH_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "verified"
    assert asset.last_checked_at is not None
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed",
        ActivityLog.note.like("%verified%"),
    ).count() == 1


def test_verify_name_absent_keeps_status_and_notes(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITHOUT_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "live"  # never auto-upgraded, never downgraded
    assert "couldn't" in note.lower() or "could not" in note.lower()


def test_verify_without_url_returns_note(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    asset, note = authority_service.verify_asset(asset, client, db)
    assert "url" in note.lower()
    assert asset.status == "missing"


def test_verify_fetch_failure_only_sets_last_checked(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", side_effect=Exception("timeout")):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "live"
    assert asset.last_checked_at is not None
    assert "reach" in note.lower() or "load" in note.lower()


def test_nap_mismatch_flagged_on_different_phone(db):
    from app.services import authority_service
    client = _make_client(db)
    client.phone = "+60 3-1234 5678"
    db.commit()
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WRONG_PHONE)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.nap_mismatch is True


def test_nap_match_when_same_digits_formatted_differently(db):
    from app.services import authority_service
    client = _make_client(db)
    client.phone = "03-1234 5678"  # same 9 significant digits as +60 3-1234 5678
    db.commit()
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITH_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.nap_mismatch is False


def test_review_snapshot_appends_in_order(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.add_review_snapshot(asset, 4.2, 31, db)
    authority_service.add_review_snapshot(asset, 4.5, 58, db)
    assert [s["count"] for s in asset.review_snapshots] == [31, 58]
    assert asset.review_snapshots[0]["rating"] == 4.2
    assert "date" in asset.review_snapshots[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: the 7 new tests FAIL (`AttributeError: ... has no attribute 'verify_asset'`); Task 2's 8 still pass.

- [ ] **Step 3: Implement**

Extend the imports at the top of `backend/app/services/authority_service.py`:

```python
import re

from app.core.time import utcnow
from app.services.brand_detection import detect_brand_mention
from app.services.url_safety import is_safe_crawl_url, safe_get
from bs4 import BeautifulSoup
```

Append the functions:

```python
_VERIFY_TIMEOUT = 10.0
# A phone candidate: a run starting with an optional + then digits/space/-/()/.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,16}\d")


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _phone_candidates(text: str) -> list[str]:
    """Digit-only phone candidates (9-13 significant digits) found in page text."""
    out: list[str] = []
    for match in _PHONE_RE.findall(text):
        digits = _digits(match)
        if 9 <= len(digits) <= 13:
            out.append(digits)
    return out


def _page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_nap(page_text: str, client: Client) -> dict:
    """Best-effort Name/Address/Phone signals from a directory page's text.

    Name = the client name when present (normalized). Phone = the first
    candidate that matches the client's phone by last-9-digit suffix, else the
    first candidate found. Address = a short window around the client's city.
    """
    name = client.name if detect_brand_mention(page_text, client.name) else None

    candidates = _phone_candidates(page_text)
    client_digits = _digits(client.phone)
    phone = None
    if client_digits:
        phone = next((c for c in candidates if c[-9:] == client_digits[-9:]), None)
    if phone is None and candidates:
        phone = candidates[0]

    address_text = None
    if client.city:
        idx = page_text.lower().find(client.city.lower())
        if idx != -1:
            start = max(0, idx - 40)
            address_text = page_text[start:idx + len(client.city) + 20].strip()

    return {"name": name, "phone": phone, "address_text": address_text}


def _nap_has_mismatch(found_nap: dict, client: Client) -> bool:
    """True only when a phone was found that disagrees with client.phone.

    No client phone on file, or no phone found on the page → not a mismatch
    (nothing to contradict). Compares the last 9 significant digits to tolerate
    country-code and separator formatting differences (spec §6)."""
    client_digits = _digits(client.phone)
    found_digits = _digits(found_nap.get("phone"))
    if not client_digits or not found_digits:
        return False
    return client_digits[-9:] != found_digits[-9:]


def verify_asset(asset: AuthorityAsset, client: Client, db: Session) -> tuple[AuthorityAsset, str]:
    """Single-page verification. Never raises; a failure sets last_checked_at
    and returns an honest note without touching status (spec §6, §10)."""
    if not asset.url:
        return asset, "Add the profile URL first, then run the check."

    note: str
    asset.last_checked_at = utcnow()
    try:
        if not is_safe_crawl_url(asset.url):
            note = "Couldn't reach that page safely — check the address."
        else:
            resp = safe_get(asset.url, timeout=_VERIFY_TIMEOUT)
            ctype = resp.headers.get("content-type", "").lower()
            if resp.status_code != 200 or ("html" not in ctype and ctype != ""):
                note = "Couldn't load that page — it didn't return a readable web page."
            else:
                text = _page_text(resp.text)
                found = extract_nap(text, client)
                asset.found_nap = found
                asset.nap_mismatch = _nap_has_mismatch(found, client)
                if found["name"]:
                    if asset.status != "verified":
                        asset.status = "verified"
                        db.add(ActivityLog(
                            client_id=asset.client_id,
                            event_type="authority_status_changed",
                            note=f"{asset.name} verified — the page names {client.name}.",
                        ))
                    note = "Verified — the page names this business."
                    if asset.nap_mismatch:
                        note += " Heads up: the phone number on the page differs from the one on file."
                else:
                    note = ("Couldn't confirm automatically — many directories load their "
                            "content in the browser. Verify by hand if the listing looks right.")
    except Exception as exc:  # network/parse — honest shrug, no status change
        logger.warning("authority_verify_failed", asset_id=str(asset.id), error=str(exc))
        note = "Couldn't reach that page — try again in a moment."

    db.commit()
    db.refresh(asset)
    return asset, note


def add_review_snapshot(
    asset: AuthorityAsset, rating: float, count: int, db: Session
) -> AuthorityAsset:
    """Append this month's {date, rating, count} to the review sparkline history."""
    snapshot = {
        "date": utcnow().date().isoformat(),
        "rating": round(float(rating), 2),
        "count": int(count),
    }
    # JSONB list needs reassignment for SQLAlchemy to detect the change.
    asset.review_snapshots = list(asset.review_snapshots or []) + [snapshot]
    db.add(ActivityLog(
        client_id=asset.client_id, event_type="review_snapshot_added",
        note=f"{asset.name}: {rating} stars, {count} reviews.",
    ))
    db.commit()
    db.refresh(asset)
    return asset
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/authority_service.py backend/tests/test_authority_service.py
git commit -m "feat(authority): verify crawler + NAP extraction + review snapshots"
```

---

### Task 4: Provenance aggregation + suggested-next + authority view

**Files:**
- Modify: `backend/app/services/authority_service.py` (append)
- Test: `backend/tests/test_authority_service.py` (append)

**Interfaces:**
- Produces:
  - `compute_provenance_counts(client_id: uuid.UUID, db: Session) -> dict[str, int]` — `{domain: count}` across all the client's completed-scan client-owned source rows.
  - `build_authority_view(client: Client, db: Session) -> dict` — `{"assets": [asset_dict...], "suggested_next": [{"domain","count","catalog_key": str|None}...], "summary": {...}}`. `asset_dict` = the asset's own columns plus `"seen_in_ai_sources": int`. Degrades to counts-less assets (no 500) if aggregation fails. Suggested-next only populated when ≥1 non-hidden asset exists.
  - `summarize_for_assessment(client_id: uuid.UUID, db: Session) -> dict | None` — compact evidence for the Brand Authority prompt, or None when the client has no assets.
- Consumes: `ScanQuerySource`, `ScanQueryResult`, `Scan` models; `func` from sqlalchemy.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_authority_service.py`:

```python
def _seed_sources(db, client, domain_counts: dict[str, int]):
    """Create one completed scan whose client-owned queries cite the given
    domains the given number of times."""
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.scan_query_source import ScanQuerySource
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    result = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best dental clinic KL", response_text="...", brand_detected=False,
    )
    db.add(result)
    db.commit()
    rank = 1
    for domain, n in domain_counts.items():
        for _ in range(n):
            db.add(ScanQuerySource(
                scan_query_result_id=result.id, url=f"https://{domain}/x{rank}",
                domain=domain, rank=rank, source_type="third_party", fetch_status="ok",
            ))
            rank += 1
    db.commit()
    return scan


def test_provenance_counts_roll_up_per_domain(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"cameragear.com": 3, "reddit.com": 2})
    counts = authority_service.compute_provenance_counts(client.id, db)
    assert counts == {"cameragear.com": 3, "reddit.com": 2}


def test_asset_seen_count_uses_suffix_match(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"maps.google.com": 4})
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)  # google.com
    view = authority_service.build_authority_view(client, db)
    gbp = next(a for a in view["assets"] if a["asset_key"] == "gbp")
    assert gbp["seen_in_ai_sources"] == 4


def test_suggested_next_excludes_covered_and_needs_an_asset(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"reddit.com": 5, "linkedin.com": 3})
    # No assets yet → no suggestions at all (spec §5).
    assert authority_service.build_authority_view(client, db)["suggested_next"] == []
    # Add + mark LinkedIn live → linkedin.com is covered, reddit.com surfaces.
    (li,) = authority_service.add_assets(client, [{"asset_key": "linkedin"}], db)
    authority_service.update_asset(li, {"status": "live"}, db)
    view = authority_service.build_authority_view(client, db)
    domains = [s["domain"] for s in view["suggested_next"]]
    assert "reddit.com" in domains
    assert "linkedin.com" not in domains
    reddit = next(s for s in view["suggested_next"] if s["domain"] == "reddit.com")
    assert reddit["count"] == 5
    assert reddit["catalog_key"] is None  # reddit isn't in the catalog


def test_suggested_next_maps_catalog_key_when_domain_known(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"crunchbase.com": 6})
    (li,) = authority_service.add_assets(client, [{"asset_key": "linkedin"}], db)
    authority_service.update_asset(li, {"status": "live"}, db)
    view = authority_service.build_authority_view(client, db)
    cb = next(s for s in view["suggested_next"] if s["domain"] == "crunchbase.com")
    assert cb["catalog_key"] == "crunchbase"


def test_summary_counts_live_and_verified(db):
    from app.services import authority_service
    client = _make_client(db)
    a1, a2 = authority_service.add_assets(
        client, [{"asset_key": "gbp"}, {"asset_key": "linkedin"}], db)
    authority_service.update_asset(a1, {"status": "verified"}, db)
    authority_service.update_asset(a2, {"status": "live"}, db)
    summary = authority_service.build_authority_view(client, db)["summary"]
    assert summary["live"] == 1
    assert summary["verified"] == 1
    assert summary["total"] == 2


def test_summarize_for_assessment_none_when_empty(db):
    from app.services import authority_service
    client = _make_client(db)
    assert authority_service.summarize_for_assessment(client.id, db) is None


def test_summarize_for_assessment_reports_verified_names(db):
    from app.services import authority_service
    client = _make_client(db)
    (gbp,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(gbp, {"status": "verified"}, db)
    summary = authority_service.summarize_for_assessment(client.id, db)
    assert summary["verified"] == 1
    assert "Google Business Profile" in summary["verified_names"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: the 7 new tests FAIL (`AttributeError: ... 'compute_provenance_counts'`); the prior 15 still pass.

- [ ] **Step 3: Implement**

Extend the imports at the top of `backend/app/services/authority_service.py`:

```python
from sqlalchemy import func

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
```

Append the functions:

```python
_SUGGESTED_NEXT_LIMIT = 8
_TOP_DOMAINS_FOR_COVERAGE = 5


def compute_provenance_counts(client_id: uuid.UUID, db: Session) -> dict[str, int]:
    """{domain: citations} across the client's completed-scan, client-owned
    source rows. The Share-of-Source acquisition signal, reused as an authority
    to-do list (spec §5)."""
    rows = (
        db.query(ScanQuerySource.domain, func.count(ScanQuerySource.id))
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .join(Scan, Scan.id == ScanQueryResult.scan_id)
        .filter(
            Scan.client_id == client_id,
            Scan.status == "completed",
            ScanQueryResult.competitor_id.is_(None),
        )
        .group_by(ScanQuerySource.domain)
        .all()
    )
    return {domain: count for domain, count in rows if domain}


def _domain_matches(source_domain: str, provenance_domain: str | None) -> bool:
    """Suffix match: google.com covers google.com and maps.google.com."""
    if not provenance_domain:
        return False
    return source_domain == provenance_domain or source_domain.endswith("." + provenance_domain)


_CATALOG_KEY_BY_DOMAIN: dict[str, str] = {
    item["provenance_domain"]: item["key"]
    for item in AUTHORITY_ASSET_CATALOG
    if item["provenance_domain"]
}


def _asset_dict(asset: AuthorityAsset, counts: dict[str, int]) -> dict:
    seen = sum(
        n for domain, n in counts.items() if _domain_matches(domain, asset.provenance_domain)
    )
    return {
        "id": str(asset.id), "asset_key": asset.asset_key, "name": asset.name,
        "asset_type": asset.asset_type, "url": asset.url, "status": asset.status,
        "notes": asset.notes, "provenance_domain": asset.provenance_domain,
        "review_snapshots": asset.review_snapshots or [], "found_nap": asset.found_nap,
        "nap_mismatch": asset.nap_mismatch,
        "last_checked_at": asset.last_checked_at.isoformat() + "Z" if asset.last_checked_at else None,
        "seen_in_ai_sources": seen,
    }


def build_authority_view(client: Client, db: Session) -> dict:
    """Assets + provenance badges + suggested-next rail + summary (spec §5, §9)."""
    assets = list_assets(client.id, db)
    try:
        counts = compute_provenance_counts(client.id, db)
    except Exception as exc:  # degrade to the plain checklist, never a 500
        logger.warning("authority_provenance_failed", client_id=str(client.id), error=str(exc))
        counts = {}

    asset_dicts = [_asset_dict(a, counts) for a in assets]

    # A domain is "covered" when a live/verified asset's provenance_domain
    # suffix-matches it. Suggested-next = uncovered domains by citation count.
    covered_domains = [
        a.provenance_domain for a in assets
        if a.status in ("live", "verified") and a.provenance_domain
    ]
    suggested_next: list[dict] = []
    if assets:  # spec §5: only once at least one asset exists
        uncovered = {
            domain: n for domain, n in counts.items()
            if not any(_domain_matches(domain, pd) for pd in covered_domains)
        }
        for domain, n in sorted(uncovered.items(), key=lambda kv: -kv[1])[:_SUGGESTED_NEXT_LIMIT]:
            suggested_next.append({
                "domain": domain, "count": n,
                "catalog_key": _CATALOG_KEY_BY_DOMAIN.get(domain),
            })

    top_domains = [d for d, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:_TOP_DOMAINS_FOR_COVERAGE]]
    covered_top = sum(
        1 for d in top_domains if any(_domain_matches(d, pd) for pd in covered_domains)
    )
    summary = {
        "total": len(assets),
        "live": sum(1 for a in assets if a.status == "live"),
        "verified": sum(1 for a in assets if a.status == "verified"),
        "covered_top_domains": covered_top,
        "total_top_domains": len(top_domains),
    }
    return {"assets": asset_dicts, "suggested_next": suggested_next, "summary": summary}


def summarize_for_assessment(client_id: uuid.UUID, db: Session) -> dict | None:
    """Compact authority evidence for the Brand Authority prompt, or None when
    the client has no assets (spec §7). Never includes internal metrics."""
    assets = list_assets(client_id, db)
    if not assets:
        return None
    by_status: dict[str, int] = {}
    for a in assets:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    verified_names = [a.name for a in assets if a.status == "verified"]
    live_names = [a.name for a in assets if a.status == "live"]
    missing_names = [a.name for a in assets if a.status == "missing"]
    return {
        "total": len(assets),
        "live": by_status.get("live", 0),
        "verified": by_status.get("verified", 0),
        "missing": by_status.get("missing", 0),
        "verified_names": verified_names,
        "live_names": live_names,
        "missing_names": missing_names,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_authority_service.py -q`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/authority_service.py backend/tests/test_authority_service.py
git commit -m "feat(authority): provenance aggregation + suggested-next + authority view"
```

---

### Task 5: API routes + schemas

**Files:**
- Create: `backend/app/schemas/authority.py`
- Create: `backend/app/api/v1/authority.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_authority_api.py`

**Interfaces:**
- Produces routes (all admin-only, `require_api_key`):
  - `GET /api/v1/clients/{id}/authority` → `AuthorityViewResponse` (assets + suggested_next + summary). Never auto-creates.
  - `GET /api/v1/clients/{id}/authority/catalog` → `list[CatalogItem]`.
  - `POST /api/v1/clients/{id}/authority` → `list[AuthorityAssetOut]` (add one or more).
  - `PATCH /api/v1/clients/{id}/authority/{asset_id}` → `AuthorityAssetOut`.
  - `POST /api/v1/clients/{id}/authority/{asset_id}/verify` → `VerifyResponse` (`{asset, note}`).
  - `POST /api/v1/clients/{id}/authority/{asset_id}/review-snapshot` → `AuthorityAssetOut`.
- Consumes: Task 2-4 service functions; `require_api_key`, `get_db`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_authority_api.py`:

```python
"""authority API — admin-only routes (spec §8). Uses the app client fixture."""
import uuid
from unittest.mock import patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_catalog_route_lists_items(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/authority/catalog", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(item["key"] == "gbp" for item in body)
    assert all(item["added"] is False for item in body)


def test_view_route_empty_for_new_client(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/authority", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["assets"] == []
    assert body["suggested_next"] == []
    assert body["summary"]["total"] == 0


def test_add_and_patch_and_view(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                    json={"items": [{"asset_key": "gbp"}]})
    assert r.status_code == 200
    asset_id = r.json()[0]["id"]
    r2 = client.patch(f"/api/v1/clients/{c.id}/authority/{asset_id}", headers=auth_headers,
                      json={"status": "live", "url": "https://g.co/acme"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "live"
    view = client.get(f"/api/v1/clients/{c.id}/authority", headers=auth_headers).json()
    assert view["summary"]["live"] == 1


def test_verify_route(client, db, auth_headers):
    from app.services.url_safety import SafeResponse
    from app.services import authority_service
    c = _make_client(db)
    add = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                      json={"items": [{"asset_key": "gbp", "url": "https://g.co/acme"}]})
    asset_id = add.json()[0]["id"]
    page = "<html><body><h1>Acme Dental</h1></body></html>"
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get",
                      return_value=SafeResponse(200, page, {"content-type": "text/html"})):
        r = client.post(f"/api/v1/clients/{c.id}/authority/{asset_id}/verify", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["asset"]["status"] == "verified"
    assert isinstance(r.json()["note"], str)


def test_review_snapshot_route(client, db, auth_headers):
    c = _make_client(db)
    add = client.post(f"/api/v1/clients/{c.id}/authority", headers=auth_headers,
                      json={"items": [{"asset_key": "gbp"}]})
    asset_id = add.json()[0]["id"]
    r = client.post(f"/api/v1/clients/{c.id}/authority/{asset_id}/review-snapshot",
                    headers=auth_headers, json={"rating": 4.5, "count": 58})
    assert r.status_code == 200
    assert r.json()["review_snapshots"][-1]["count"] == 58


def test_routes_require_auth(client, db):
    c = _make_client(db)
    assert client.get(f"/api/v1/clients/{c.id}/authority").status_code in (401, 403)


def test_patch_unknown_asset_404s(client, db, auth_headers):
    c = _make_client(db)
    r = client.patch(f"/api/v1/clients/{c.id}/authority/{uuid.uuid4()}",
                     headers=auth_headers, json={"status": "live"})
    assert r.status_code == 404
```

Note: reuse whatever fixtures the existing API tests use. If the fixtures are named differently (e.g. `test_client` instead of `client`, or a headers helper), copy the exact fixture usage from an existing file such as `backend/tests/test_citability_api.py` — do not invent fixture names.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_authority_api.py -q`
Expected: FAIL — 404s on every route (router not wired yet).

- [ ] **Step 3: Implement the schemas**

`backend/app/schemas/authority.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class CatalogItem(BaseModel):
    key: str
    name: str
    type: str
    provenance_domain: str | None
    url_hint: str | None
    suggested_industries: list[str]
    added: bool


class ReviewSnapshot(BaseModel):
    date: str
    rating: float
    count: int


class AuthorityAssetOut(BaseModel):
    id: uuid.UUID
    asset_key: str | None
    name: str
    asset_type: str
    url: str | None
    status: str
    notes: str | None
    provenance_domain: str | None
    review_snapshots: list[ReviewSnapshot]
    found_nap: dict | None
    nap_mismatch: bool
    last_checked_at: datetime | None
    seen_in_ai_sources: int = 0

    model_config = {"from_attributes": True}


class SuggestedDomain(BaseModel):
    domain: str
    count: int
    catalog_key: str | None


class AuthoritySummary(BaseModel):
    total: int
    live: int
    verified: int
    covered_top_domains: int
    total_top_domains: int


class AuthorityViewResponse(BaseModel):
    assets: list[AuthorityAssetOut]
    suggested_next: list[SuggestedDomain]
    summary: AuthoritySummary


class AddAssetItem(BaseModel):
    asset_key: str | None = None
    name: str | None = None
    asset_type: str | None = None
    url: str | None = None
    provenance_domain: str | None = None


class AddAssetsRequest(BaseModel):
    items: list[AddAssetItem]


class PatchAssetRequest(BaseModel):
    status: str | None = None
    url: str | None = None
    notes: str | None = None
    hidden: bool | None = None


class ReviewSnapshotRequest(BaseModel):
    rating: float
    count: int


class VerifyResponse(BaseModel):
    asset: AuthorityAssetOut
    note: str
```

- [ ] **Step 4: Implement the routes**

`backend/app/api/v1/authority.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import AUTHORITY_ASSET_STATUSES
from app.core.database import get_db
from app.models.authority_asset import AuthorityAsset
from app.models.client import Client
from app.schemas.authority import (
    AddAssetsRequest,
    AuthorityAssetOut,
    AuthorityViewResponse,
    CatalogItem,
    PatchAssetRequest,
    ReviewSnapshotRequest,
    VerifyResponse,
)
from app.services import authority_service

router = APIRouter(prefix="/clients/{client_id}/authority", tags=["authority"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _get_asset_or_404(client_id: uuid.UUID, asset_id: uuid.UUID, db: Session) -> AuthorityAsset:
    asset = db.get(AuthorityAsset, asset_id)
    if not asset or asset.client_id != client_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def _out(asset: AuthorityAsset, seen: int = 0) -> AuthorityAssetOut:
    data = AuthorityAssetOut.model_validate(asset)
    data.seen_in_ai_sources = seen
    return data


@router.get("", response_model=AuthorityViewResponse, dependencies=[Depends(require_api_key)])
def get_authority(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    return authority_service.build_authority_view(client, db)


@router.get("/catalog", response_model=list[CatalogItem], dependencies=[Depends(require_api_key)])
def get_catalog(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    return authority_service.get_catalog(client, db)


@router.post("", response_model=list[AuthorityAssetOut], dependencies=[Depends(require_api_key)])
def add_assets(client_id: uuid.UUID, body: AddAssetsRequest, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    rows = authority_service.add_assets(client, [i.model_dump() for i in body.items], db)
    return [_out(r) for r in rows]


@router.patch("/{asset_id}", response_model=AuthorityAssetOut, dependencies=[Depends(require_api_key)])
def patch_asset(
    client_id: uuid.UUID, asset_id: uuid.UUID, body: PatchAssetRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    patch = body.model_dump(exclude_unset=True)
    if "status" in patch and patch["status"] not in AUTHORITY_ASSET_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    asset = authority_service.update_asset(asset, patch, db)
    return _out(asset)


@router.post("/{asset_id}/verify", response_model=VerifyResponse, dependencies=[Depends(require_api_key)])
def verify(client_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    asset, note = authority_service.verify_asset(asset, client, db)
    return VerifyResponse(asset=_out(asset), note=note)


@router.post("/{asset_id}/review-snapshot", response_model=AuthorityAssetOut, dependencies=[Depends(require_api_key)])
def review_snapshot(
    client_id: uuid.UUID, asset_id: uuid.UUID, body: ReviewSnapshotRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    asset = authority_service.add_review_snapshot(asset, body.rating, body.count, db)
    return _out(asset)
```

In `backend/app/api/v1/router.py`: add `authority` to the `from app.api.v1 import ...` line and add `router.include_router(authority.router)` at the end.

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/test_authority_api.py -q`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/authority.py backend/app/api/v1/authority.py backend/app/api/v1/router.py backend/tests/test_authority_api.py
git commit -m "feat(authority): admin API routes + schemas"
```

---

### Task 6: Brand Authority assessment evidence block

**Files:**
- Modify: `backend/app/prompts/assessment.py` (add authority block; bump version)
- Modify: `backend/app/services/assessment_service.py` (compute + pass authority summary)
- Test: `backend/tests/test_assessment_authority.py`

**Interfaces:**
- Produces: `build_assessment_prompt(client, dimension, crawl=None, authority=None)`; `_brand_authority_prompt(client, authority=None)`; `BRAND_AUTHORITY_VERSION = "v3"`.
- Consumes: `authority_service.summarize_for_assessment`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_assessment_authority.py`:

```python
"""Brand Authority assessment consumes the authority-asset evidence (spec §7)."""


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_prompt_includes_authority_evidence_when_present():
    from app.models.client import Client
    from app.prompts.assessment import build_assessment_prompt
    client = Client(name="Acme Dental", website="https://acme.com",
                    industry="Dental clinic", contact_email="x@acme.com")
    authority = {
        "total": 3, "live": 1, "verified": 1, "missing": 1,
        "verified_names": ["Google Business Profile"], "live_names": ["LinkedIn company page"],
        "missing_names": ["Crunchbase"],
    }
    prompt = build_assessment_prompt(client, "brand_authority", authority=authority)
    assert "Google Business Profile" in prompt
    assert "verified" in prompt.lower()


def test_prompt_omits_block_when_no_authority():
    from app.models.client import Client
    from app.prompts.assessment import build_assessment_prompt
    client = Client(name="Acme Dental", website="https://acme.com",
                    industry="Dental clinic", contact_email="x@acme.com")
    prompt = build_assessment_prompt(client, "brand_authority", authority=None)
    assert "SeenBy-tracked authority assets" not in prompt


def test_version_bumped_to_v3():
    from app.prompts.assessment import BRAND_AUTHORITY_VERSION
    assert BRAND_AUTHORITY_VERSION == "v3"


def test_generate_assessment_passes_authority(db):
    """brand_authority assessment pulls the authority summary and it reaches the prompt."""
    from unittest.mock import MagicMock, patch
    from app.services import assessment_service, authority_service
    client = _make_client(db)
    (gbp,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(gbp, {"status": "verified"}, db)

    captured = {}

    def fake_build(cl, dim, crawl=None, authority=None):
        captured["authority"] = authority
        return "PROMPT"

    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(text='{"score": 60, "bullets": ["ok"], "narrative": "n"}')]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    with patch.object(assessment_service, "build_assessment_prompt", side_effect=fake_build), \
         patch.object(assessment_service, "anthropic_client", return_value=ac), \
         patch.object(assessment_service, "record_llm_call"):
        assessment_service.generate_assessment(client, "brand_authority", db)
    assert captured["authority"] is not None
    assert captured["authority"]["verified"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_assessment_authority.py -q`
Expected: FAIL — `build_assessment_prompt() got an unexpected keyword argument 'authority'` and `BRAND_AUTHORITY_VERSION == "v2"`.

- [ ] **Step 3: Implement the prompt change**

In `backend/app/prompts/assessment.py`:

1. Bump the version constant:

```python
# v3: adds a SeenBy-tracked authority-asset evidence block (Phase 4) — the
# assessment now reasons over the admin-curated directory/review/social
# checklist, not just an outside web search.
BRAND_AUTHORITY_VERSION = "v3"
```

2. Add an authority-block helper above `_brand_authority_prompt`:

```python
def _authority_block(authority: dict | None) -> str:
    if not authority:
        return ""
    lines = [
        f"- Verified profiles: {', '.join(authority['verified_names']) or 'none'}",
        f"- Live (unverified) profiles: {', '.join(authority['live_names']) or 'none'}",
        f"- Not yet set up: {', '.join(authority['missing_names']) or 'none'}",
    ]
    joined = "\n".join(lines)
    return f"""

SeenBy-tracked authority assets for this business (admin-curated checklist — treat as confirmed facts, not guesses):
{joined}
Weigh verified profiles as strong presence signals and the not-yet-set-up ones as gaps. Do NOT invent profiles beyond this list; anything not listed is unknown, so phrase it as "To verify: …"."""
```

3. Thread `authority` through the two functions:

```python
def _brand_authority_prompt(client: Client, authority: dict | None = None) -> str:
    loc = _location(client)
    return f"""You assess the BRAND AUTHORITY of a {client.industry} business called {client.name}{f" based in {loc}" if loc else ""} for AI search visibility.
Website: {client.website}. Business context: {client.description or "n/a"}.

Brand Authority measures how strongly AI models recognise this brand as a real, trusted entity, based on PUBLIC signals an outsider could verify:
- Presence and engagement on high-AI-weight platforms (YouTube, Reddit, Wikipedia/Wikidata, LinkedIn).
- Third-party reviews and directory listings (Google, G2, Trustpilot, industry directories).
- Branded search demand and consistent name/usage across the web.{_authority_block(authority)}

Score 0-100 where 80-100 = a widely-recognised authority, 50-64 = present but thin, 0-34 = almost no public footprint.
Each bullet is either a public fact you confirmed via search (e.g. "Listed on Google with 40+ reviews at 4.6 stars") or a "To verify: …" item — never an unconfirmed assertion, never an internal metric.
{_EVIDENCE_RULES}
{_LANGUAGE_RULES}
{_JSON_CONTRACT}"""
```

and update the dispatcher:

```python
def build_assessment_prompt(
    client: Client, dimension: str, crawl: dict | None = None, authority: dict | None = None
) -> str:
    if dimension == DIMENSION_BRAND_AUTHORITY:
        return _brand_authority_prompt(client, authority=authority)
    if dimension == DIMENSION_CONTENT_QUALITY:
        return _content_quality_prompt(client, crawl=crawl)
    raise ValueError(f"unknown dimension: {dimension}")
```

- [ ] **Step 4: Wire the service to compute + pass it**

In `backend/app/services/assessment_service.py`:

1. Add the import near the top (after the existing `from app.prompts.assessment import ...`):

```python
from app.services import authority_service
```

2. In `generate_assessment`, compute the authority summary for the brand_authority dimension and pass it into the prompt. Replace the `crawl = ...` line and the `messages=[...]` line inside the `try`:

```python
        service = _SERVICE_BY_DIMENSION[dimension]
        crawl = _latest_crawl(client.id, db) if dimension == "content_quality" else None
        authority = (
            authority_service.summarize_for_assessment(client.id, db)
            if dimension == "brand_authority" else None
        )
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=_MAX_TOKENS,
            temperature=0,
            tools=[_WEB_SEARCH_TOOL],
            messages=[{"role": "user",
                       "content": build_assessment_prompt(client, dimension, crawl=crawl, authority=authority)}],
        )
```

- [ ] **Step 5: Run the tests + guard the registry version test**

Run: `poetry run pytest tests/test_assessment_authority.py -q`
Expected: 4 passed.

Then check whether any existing test pins the old version string, and fix it if so:

```bash
grep -rn "brand_authority.*v2\|BRAND_AUTHORITY_VERSION" backend/tests/ backend/app/prompts/registry.py
```
If a test asserts `"v2"` for brand authority, update that assertion to `"v3"` (the registry reads the constant, so `registry.py` itself needs no edit). Re-run that test file to confirm green.

- [ ] **Step 6: Full backend suite**

Run: `poetry run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/prompts/assessment.py backend/app/services/assessment_service.py backend/tests/test_assessment_authority.py
git commit -m "feat(authority): feed authority assets into Brand Authority assessment (prompt v3)"
```

---

### Task 7: Frontend — /authority page + settings phone + nav

**Files:**
- Create: `frontend/src/app/clients/[id]/authority/page.tsx`
- Create: `frontend/src/app/clients/[id]/authority/actions.ts`
- Create: `frontend/src/app/clients/[id]/authority/AuthorityClient.tsx`
- Create: `frontend/src/app/clients/[id]/authority/CatalogPicker.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` + `settings/actions.ts`
- Modify: `CLAUDE.md` (§9)

**Interfaces:**
- Consumes the six Task 5 routes via new `api.ts` functions.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, add `phone: string | null` to the `Client` interface (next to `city/state/country`), and append the authority types:

```typescript
// --- Authority & Presence Tracker (Phase 4) ---
export type AuthorityAssetType =
  | "directory" | "review_platform" | "social" | "knowledge_graph" | "media" | "other"
export type AuthorityStatus = "missing" | "in_progress" | "live" | "verified"

export interface AuthorityReviewSnapshot {
  date: string
  rating: number
  count: number
}
export interface AuthorityAsset {
  id: string
  asset_key: string | null
  name: string
  asset_type: AuthorityAssetType
  url: string | null
  status: AuthorityStatus
  notes: string | null
  provenance_domain: string | null
  review_snapshots: AuthorityReviewSnapshot[]
  found_nap: { name?: string | null; phone?: string | null; address_text?: string | null } | null
  nap_mismatch: boolean
  last_checked_at: string | null
  seen_in_ai_sources: number
}
export interface AuthorityCatalogItem {
  key: string
  name: string
  type: AuthorityAssetType
  provenance_domain: string | null
  url_hint: string | null
  suggested_industries: string[]
  added: boolean
}
export interface AuthoritySuggestedDomain {
  domain: string
  count: number
  catalog_key: string | null
}
export interface AuthoritySummary {
  total: number
  live: number
  verified: number
  covered_top_domains: number
  total_top_domains: number
}
export interface AuthorityView {
  assets: AuthorityAsset[]
  suggested_next: AuthoritySuggestedDomain[]
  summary: AuthoritySummary
}
export interface AuthorityVerifyResponse {
  asset: AuthorityAsset
  note: string
}
export interface AddAuthorityAssetItem {
  asset_key?: string
  name?: string
  asset_type?: AuthorityAssetType
  url?: string
  provenance_domain?: string
}
```

- [ ] **Step 2: Add api.ts functions**

Append to `frontend/src/lib/api.ts` (near the other client-scoped calls). `apiFetch` is the existing helper:

```typescript
export async function getAuthorityView(clientId: string): Promise<AuthorityView> {
  return apiFetch<AuthorityView>(`/api/v1/clients/${clientId}/authority`)
}
export async function getAuthorityCatalog(clientId: string): Promise<AuthorityCatalogItem[]> {
  return apiFetch<AuthorityCatalogItem[]>(`/api/v1/clients/${clientId}/authority/catalog`)
}
export async function addAuthorityAssets(
  clientId: string, items: AddAuthorityAssetItem[],
): Promise<AuthorityAsset[]> {
  return apiFetch<AuthorityAsset[]>(`/api/v1/clients/${clientId}/authority`, {
    method: "POST", body: JSON.stringify({ items }),
  })
}
export async function patchAuthorityAsset(
  clientId: string, assetId: string,
  patch: { status?: AuthorityStatus; url?: string; notes?: string; hidden?: boolean },
): Promise<AuthorityAsset> {
  return apiFetch<AuthorityAsset>(`/api/v1/clients/${clientId}/authority/${assetId}`, {
    method: "PATCH", body: JSON.stringify(patch),
  })
}
export async function verifyAuthorityAsset(
  clientId: string, assetId: string,
): Promise<AuthorityVerifyResponse> {
  return apiFetch<AuthorityVerifyResponse>(
    `/api/v1/clients/${clientId}/authority/${assetId}/verify`, { method: "POST" },
  )
}
export async function addAuthorityReviewSnapshot(
  clientId: string, assetId: string, rating: number, count: number,
): Promise<AuthorityAsset> {
  return apiFetch<AuthorityAsset>(
    `/api/v1/clients/${clientId}/authority/${assetId}/review-snapshot`,
    { method: "POST", body: JSON.stringify({ rating, count }) },
  )
}
```

Ensure the new type names are added to the existing `import type { ... } from "@/types"` block at the top of `api.ts` (`AuthorityView`, `AuthorityCatalogItem`, `AuthorityAsset`, `AuthorityStatus`, `AuthorityVerifyResponse`, `AddAuthorityAssetItem`).

- [ ] **Step 3: Server actions**

`frontend/src/app/clients/[id]/authority/actions.ts`:

```typescript
"use server"

import { revalidatePath } from "next/cache"
import {
  addAuthorityAssets,
  patchAuthorityAsset,
  verifyAuthorityAsset,
  addAuthorityReviewSnapshot,
} from "@/lib/api"
import type {
  AddAuthorityAssetItem, AuthorityAsset, AuthorityStatus, AuthorityVerifyResponse,
} from "@/types"

const path = (clientId: string) => `/clients/${clientId}/authority`

export async function addAssetsAction(
  clientId: string, items: AddAuthorityAssetItem[],
): Promise<AuthorityAsset[]> {
  const rows = await addAuthorityAssets(clientId, items)
  revalidatePath(path(clientId))
  return rows
}

export async function patchAssetAction(
  clientId: string, assetId: string,
  patch: { status?: AuthorityStatus; url?: string; notes?: string; hidden?: boolean },
): Promise<AuthorityAsset> {
  const row = await patchAuthorityAsset(clientId, assetId, patch)
  revalidatePath(path(clientId))
  return row
}

export async function verifyAssetAction(
  clientId: string, assetId: string,
): Promise<AuthorityVerifyResponse> {
  const res = await verifyAuthorityAsset(clientId, assetId)
  revalidatePath(path(clientId))
  return res
}

export async function addReviewSnapshotAction(
  clientId: string, assetId: string, rating: number, count: number,
): Promise<AuthorityAsset> {
  const row = await addAuthorityReviewSnapshot(clientId, assetId, rating, count)
  revalidatePath(path(clientId))
  return row
}
```

- [ ] **Step 4: The page (server component)**

`frontend/src/app/clients/[id]/authority/page.tsx`:

```typescript
import { getAuthorityView, getAuthorityCatalog } from "@/lib/api"
import { AuthorityClient } from "./AuthorityClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function AuthorityPage({ params }: Props) {
  const { id } = await params
  const [view, catalog] = await Promise.all([
    getAuthorityView(id).catch(() => ({
      assets: [], suggested_next: [],
      summary: { total: 0, live: 0, verified: 0, covered_top_domains: 0, total_top_domains: 0 },
    })),
    getAuthorityCatalog(id).catch(() => []),
  ])
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-xl font-semibold tracking-tight">Authority &amp; Presence</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Track this client&apos;s directory, review, social, and knowledge-graph presence — prioritised
          by the sources AI answers actually drew from.
        </p>
      </div>
      <AuthorityClient clientId={id} initialView={view} catalog={catalog} />
    </div>
  )
}
```

- [ ] **Step 5: The catalog picker (client component)**

`frontend/src/app/clients/[id]/authority/CatalogPicker.tsx`:

```typescript
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import type { AuthorityCatalogItem } from "@/types"

interface Props {
  catalog: AuthorityCatalogItem[]
  onAdd: (keys: string[]) => Promise<void>
  pending: boolean
}

export function CatalogPicker({ catalog, onAdd, pending }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const selectable = catalog.filter((c) => !c.added)

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  if (selectable.length === 0) {
    return <p className="text-sm text-muted-foreground">Every catalog item has been added.</p>
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {selectable.map((item) => (
          <label
            key={item.key}
            htmlFor={`cat-${item.key}`}
            className="flex items-start gap-2 rounded-md border p-2.5 text-sm cursor-pointer hover:bg-muted/50"
          >
            <Checkbox
              id={`cat-${item.key}`}
              checked={selected.has(item.key)}
              onCheckedChange={() => toggle(item.key)}
            />
            <span>
              <span className="font-medium">{item.name}</span>
              <span className="block text-xs text-muted-foreground">{item.type.replace("_", " ")}</span>
            </span>
          </label>
        ))}
      </div>
      <Button
        size="sm"
        disabled={selected.size === 0 || pending}
        onClick={async () => {
          await onAdd([...selected])
          setSelected(new Set())
        }}
      >
        Add selected ({selected.size})
      </Button>
    </div>
  )
}
```

If `@/components/ui/checkbox` does not exist, add it once with `npx shadcn@latest add checkbox` (from `frontend/`) — it is a standard shadcn component and the project uses shadcn exclusively.

- [ ] **Step 6: The main client component**

`frontend/src/app/clients/[id]/authority/AuthorityClient.tsx`:

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
import type {
  AuthorityAsset, AuthorityCatalogItem, AuthorityStatus, AuthorityView,
} from "@/types"
import { CatalogPicker } from "./CatalogPicker"
import {
  addAssetsAction, patchAssetAction, verifyAssetAction, addReviewSnapshotAction,
} from "./actions"

const STATUSES: AuthorityStatus[] = ["missing", "in_progress", "live", "verified"]
const STATUS_LABEL: Record<AuthorityStatus, string> = {
  missing: "Missing", in_progress: "In progress", live: "Live", verified: "Verified",
}

export function AuthorityClient({
  clientId, initialView, catalog,
}: {
  clientId: string
  initialView: AuthorityView
  catalog: AuthorityCatalogItem[]
}) {
  const [view, setView] = useState(initialView)
  const [showPicker, setShowPicker] = useState(initialView.assets.length === 0)
  const [pending, setPending] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  async function reloadAfter<T>(fn: () => Promise<T>): Promise<T> {
    setPending(true)
    try {
      return await fn()
    } finally {
      setPending(false)
    }
  }

  function replaceAsset(updated: AuthorityAsset) {
    setView((v) => ({ ...v, assets: v.assets.map((a) => (a.id === updated.id ? updated : a)) }))
  }

  async function handleAdd(keys: string[]) {
    await reloadAfter(async () => {
      await addAssetsAction(clientId, keys.map((k) => ({ asset_key: k })))
      // Server action revalidated the route; pull the fresh view so badges/summary update.
      window.location.reload()
    })
  }

  const s = view.summary
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-4 text-sm">
          <span><strong>{s.live}</strong> live</span>
          <span><strong>{s.verified}</strong> verified</span>
          <span className="text-muted-foreground">
            Covers {s.covered_top_domains} of your top {s.total_top_domains || 0} AI source domains
          </span>
          <Button size="sm" variant="outline" className="ml-auto"
                  onClick={() => setShowPicker((x) => !x)}>
            {showPicker ? "Hide catalog" : "Add from catalog"}
          </Button>
        </CardContent>
      </Card>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}

      {showPicker && (
        <Card>
          <CardHeader><CardTitle className="text-base">Add authority assets</CardTitle></CardHeader>
          <CardContent>
            <CatalogPicker catalog={catalog} onAdd={handleAdd} pending={pending} />
          </CardContent>
        </Card>
      )}

      {view.suggested_next.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Suggested next</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Sources AI answers drew from where this client has no live listing yet.
            </p>
            {view.suggested_next.map((d) => (
              <div key={d.domain} className="flex items-center gap-2 text-sm">
                <Badge variant="secondary">{d.count}×</Badge>
                <span className="font-medium">{d.domain}</span>
                {d.catalog_key && (
                  <Button size="sm" variant="ghost" className="ml-auto" disabled={pending}
                          onClick={() => handleAdd([d.catalog_key as string])}>
                    Add as target
                  </Button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {view.assets.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No authority assets yet. Add the ones relevant to this client from the catalog above.
        </p>
      ) : (
        <div className="space-y-3">
          {view.assets.map((asset) => (
            <Card key={asset.id}>
              <CardContent className="space-y-3 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{asset.name}</span>
                  <Badge variant="outline">{asset.asset_type.replace("_", " ")}</Badge>
                  {asset.seen_in_ai_sources > 0 && (
                    <Badge variant="secondary">Seen in AI sources {asset.seen_in_ai_sources}×</Badge>
                  )}
                  {asset.nap_mismatch && (
                    <Badge variant="destructive">Phone differs from file</Badge>
                  )}
                  <div className="ml-auto w-40">
                    <Select
                      value={asset.status}
                      onValueChange={(value) =>
                        reloadAfter(async () =>
                          replaceAsset(await patchAssetAction(clientId, asset.id, { status: value as AuthorityStatus })))
                      }
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {STATUSES.map((st) => (
                          <SelectItem key={st} value={st}>{STATUS_LABEL[st]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    defaultValue={asset.url ?? ""}
                    placeholder="Profile URL"
                    className="max-w-md"
                    onBlur={(e) =>
                      e.target.value !== (asset.url ?? "") &&
                      reloadAfter(async () =>
                        replaceAsset(await patchAssetAction(clientId, asset.id, { url: e.target.value })))
                    }
                  />
                  <Button size="sm" variant="outline" disabled={pending || !asset.url}
                          onClick={() =>
                            reloadAfter(async () => {
                              const res = await verifyAssetAction(clientId, asset.id)
                              replaceAsset(res.asset)
                              setNote(res.note)
                            })}>
                    Verify
                  </Button>
                  {asset.last_checked_at && (
                    <span className="text-xs text-muted-foreground">
                      Checked {new Date(asset.last_checked_at).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {asset.asset_type === "review_platform" && (
                  <ReviewSnapshotRow clientId={clientId} asset={asset} onUpdated={replaceAsset}
                                     pending={pending} run={reloadAfter} />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null
  const max = Math.max(...points), min = Math.min(...points)
  const span = max - min || 1
  const d = points
    .map((p, i) => `${(i / (points.length - 1)) * 100},${20 - ((p - min) / span) * 18}`)
    .join(" ")
  return (
    <svg viewBox="0 0 100 20" className="h-5 w-24" preserveAspectRatio="none" aria-hidden>
      <polyline points={d} fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
    </svg>
  )
}

function ReviewSnapshotRow({
  clientId, asset, onUpdated, pending, run,
}: {
  clientId: string
  asset: AuthorityAsset
  onUpdated: (a: AuthorityAsset) => void
  pending: boolean
  run: <T>(fn: () => Promise<T>) => Promise<T>
}) {
  const [rating, setRating] = useState("")
  const [count, setCount] = useState("")
  const snaps = asset.review_snapshots
  const latest = snaps[snaps.length - 1]
  return (
    <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-sm">
      {latest && (
        <span className="text-muted-foreground">
          {latest.rating}★ · {latest.count} reviews
        </span>
      )}
      <Sparkline points={snaps.map((s) => s.count)} />
      <Input value={rating} onChange={(e) => setRating(e.target.value)}
             placeholder="Rating" className="h-8 w-20" inputMode="decimal" />
      <Input value={count} onChange={(e) => setCount(e.target.value)}
             placeholder="Reviews" className="h-8 w-24" inputMode="numeric" />
      <Button size="sm" variant="outline"
              disabled={pending || !rating || !count}
              onClick={() =>
                run(async () => {
                  onUpdated(await addReviewSnapshotAction(clientId, asset.id, Number(rating), Number(count)))
                  setRating(""); setCount("")
                })}>
        Add this month
      </Button>
    </div>
  )
}
```

- [ ] **Step 7: Sidebar nav entry**

In `frontend/src/components/layout/Sidebar.tsx`, add an icon to the `lucide-react` import (e.g. `Award`) and insert this nav item right after the `content-studio` entry (line 38):

```typescript
  { href: "/authority",  label: "Authority & Presence", icon: Award },
```

- [ ] **Step 8: Settings phone field**

In `frontend/src/app/clients/[id]/settings/SettingsForm.tsx`, add a phone input next to the country/state/city block (around line 471-481):

```tsx
        <div>
          <Label htmlFor="s-phone">Phone</Label>
          <Input id="s-phone" name="phone" defaultValue={client.phone ?? ""} />
        </div>
```

and include it in the `updateClientAction(...)` payload (around line 271):

```typescript
          phone: (fd.get("phone") as string) || undefined,
```

In `frontend/src/app/clients/[id]/settings/actions.ts`, add `phone?: string` to the `updateClientAction` data type (near `city?/state?/country?`, line 16-18).

- [ ] **Step 9: CLAUDE.md §9**

In `CLAUDE.md` §9 (Admin Panel Navigation), add this line after the `content-studio` route:

```
/clients/[id]/authority  → authority & presence (directory/review/social checklist, provenance-prioritised)
```

- [ ] **Step 10: Verify the frontend build**

Run (from `frontend/`):
```bash
rtk tsc && rtk next build
```
Expected: typecheck clean, build succeeds, `/clients/[id]/authority` in the route list.

- [ ] **Step 11: Commit**

```bash
git add frontend/src CLAUDE.md
git commit -m "feat(authority): /authority admin page + settings phone + nav + CLAUDE.md §9"
```

---

### Task 8: Definition-of-done gate + live walkthrough

**Files:** none (verification only).

- [ ] **Step 1: Run the seenby-verify gate**

Invoke the `seenby-verify` skill and run everything it specifies:
- `poetry run pytest -q` (backend, from `backend/`) — all green.
- `rtk tsc && rtk next build` (frontend) — clean.
- Banned-language scan across the diff (no "cited/mentioned/citation rate/..." on any client-facing or stored string).
- `poetry run alembic heads` — exactly one head (the new revision).

Fix anything that fails before proceeding; do not claim done on assumption.

- [ ] **Step 2: Confirm the migration is release-ready (do NOT apply here)**

The prod migration runs at release via the `seenby-release` runbook, not in development (`.env` points at prod Supabase). Confirm the chain is clean in a throwaway check only if a clean worktree is available (the Phase 1 lesson: an untracked migration is invisible to `alembic heads` and the SQLite suite). Verify the new migration file is committed (`git status` shows it tracked).

- [ ] **Step 3: Live walkthrough (browser, admin login required)**

With the app running (`run-app` skill) and logged in as admin:
1. Open a real client → **Authority & Presence**. Confirm the empty state shows the catalog picker.
2. Pick 2-3 relevant assets (e.g. Google Business Profile, LinkedIn) → **Add selected**. Rows appear as `missing`.
3. Set one to `live`, paste its real URL, click **Verify** — confirm it flips to `verified` when the page names the client, or shows the honest "couldn't confirm" note otherwise. Confirm a NAP mismatch chip appears if the client's `phone` (set it in Settings first) differs from the page.
4. On a review platform asset, add a rating/review count; confirm the sparkline renders after a second snapshot.
5. If the client has completed scans with provenance data, confirm the **Suggested next** rail lists uncovered source domains and "Add as target" works for catalog domains.
6. Regenerate the Brand Authority assessment (on the client detail / dimensions surface) and confirm its evidence bullets now reference the tracked assets.

- [ ] **Step 4: Update project memory**

Update `seenby-geo-endtoend-roadmap.md`: mark Phase 4 complete with the merge commit, prod-migration status, and what remains (live walkthrough sign-off if deferred). Note that Phase 5 (Retainer packaging) is the last phase and consumes Phase 4's `authority_status_changed` / `review_snapshot_added` activity-log events in its work log.

- [ ] **Step 5: Finish the branch**

Invoke `superpowers:finishing-a-development-branch` to decide merge vs PR, then merge to master following the established Phase 1-3 pattern (fast-forward, delete the feature branch, re-run the full suite on master).

---

## Self-Review

**Spec coverage:**
- §3 data model → Task 1 (AuthorityAsset + client.phone, RLS, partial-unique key). ✓
- §4 master catalog, admin-picks, no auto-seed, industry sort, custom assets, soft-hide → Tasks 2 (catalog/add/idempotent/custom/hidden) + 5 (routes). ✓
- §5 provenance-driven priorities, suggested-next, "add as target", language rule → Task 4 + Task 7 (rail, "sources AI answers drew from"). ✓
- §6 verify crawler, name-match → verified, NAP extraction, digits-suffix compare, no auto-downgrade, review snapshots + activity logs → Task 3. ✓
- §7 Brand Authority assessment context block → Task 6 (prompt v3 + service wiring). ✓
- §8 six API routes, admin-only, never auto-creates → Task 5. ✓
- §9 frontend page (empty-state picker, suggested rail, grouped table, NAP chip, review sparkline, summary header), settings phone, §9 nav update → Task 7. ✓
- §10 error handling (verify failure untouched-except-last_checked, idempotent add, provenance degrades not 500) → Tasks 2/3/4 tests. ✓
- §11 testing list → Tasks 1-6 tests + Task 8 gate. ✓
- §12 build order → Tasks 1-8 mirror it (migration → catalog/CRUD → verify/NAP/reviews → provenance/suggested → assessment → frontend/settings → verify+walkthrough). ✓

**Placeholder scan:** No TBD/TODO/"add error handling"/"similar to Task N" — every step carries real code or an exact command. ✓

**Type consistency:** `verify_asset` returns `tuple[AuthorityAsset, str]` in Task 3 and the route unpacks `(asset, note)` in Task 5. `build_authority_view` returns `{assets, suggested_next, summary}` in Task 4 and the schema `AuthorityViewResponse` + `page.tsx` fallback match those keys. `_asset_dict` emits `seen_in_ai_sources`; `AuthorityAssetOut` carries it (default 0) and the route `_out` sets it — note the view route returns raw dicts (not `_out`), so the dicts already include `seen_in_ai_sources`. `summarize_for_assessment` keys (`verified_names/live_names/missing_names/total/live/verified/missing`) match `_authority_block`'s reads in Task 6. `catalog_key` (suggested-next) vs `asset_key` (asset) kept distinct. ✓

One integration note surfaced by review, folded in as guidance rather than a code change: the POST-add handler in `AuthorityClient` calls `window.location.reload()` after the server action so the recomputed `summary`/`suggested_next`/`added` flags refresh wholesale — simpler and less bug-prone than reconciling three derived structures client-side. Per-asset patch/verify/review actions update in place (they don't change the catalog or suggested rail materially enough to require a full reload).
