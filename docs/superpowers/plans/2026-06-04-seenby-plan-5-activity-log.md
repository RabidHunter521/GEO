# SeenBy Plan 5: Client Activity Log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Client Activity Log — a backend endpoint that returns the 50 most recent logged events for a client, plus a frontend `/clients/[id]/activity` page that replaces the current placeholder with a real chronological feed; also instrument toolkit and client-create endpoints to write ActivityLog rows so the feed has data beyond scans.

**Architecture:** The `activity_log` table and `ActivityLog` model already exist; `scan_service.py` already writes `scan_completed` rows. Plan 5 adds: (1) a `GET /api/v1/clients/{client_id}/activity` route that queries the table ordered newest-first; (2) `ActivityLog` writes in the toolkit generate/verify endpoints and the client create endpoint; (3) a `scan_failed` log in the except branch of `scan_service.py`; (4) the frontend page as a pure async server component. No DB migration required.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Pydantic v2 · Next.js 15 · TypeScript · shadcn/ui · lucide-react

---

## File Map

```
backend/
├── app/
│   ├── schemas/
│   │   └── activity.py                     CREATE — ActivityLogEntry schema
│   ├── api/v1/
│   │   ├── activity.py                     CREATE — GET /activity route
│   │   ├── router.py                       MODIFY — include activity router
│   │   ├── toolkit.py                      MODIFY — log toolkit_generated + toolkit_verified
│   │   └── clients.py                      MODIFY — log client_created on POST
│   └── services/
│       └── scan_service.py                 MODIFY — log scan_failed in except branch
└── tests/
    └── test_api_activity.py                CREATE

frontend/
└── src/
    ├── types/
    │   └── index.ts                        MODIFY — append ActivityLogEntry interface
    ├── lib/
    │   └── api.ts                          MODIFY — add getActivityLog function
    └── app/clients/[id]/activity/
        └── page.tsx                        MODIFY — replace placeholder
```

---

## Task 1: Backend — Schema + Endpoint + Register Router

**Files:**
- Create: `backend/app/schemas/activity.py`
- Create: `backend/app/api/v1/activity.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: Create the schema**

Create `backend/app/schemas/activity.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class ActivityLogEntry(BaseModel):
    id: uuid.UUID
    event_type: str
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create the activity router**

Create `backend/app/api/v1/activity.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.activity_log import ActivityLog
from app.schemas.activity import ActivityLogEntry

router = APIRouter(prefix="/clients/{client_id}/activity", tags=["activity"])


@router.get(
    "",
    response_model=list[ActivityLogEntry],
    dependencies=[Depends(require_api_key)],
)
def list_activity(
    client_id: uuid.UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.client_id == client_id)
        .order_by(desc(ActivityLog.created_at))
        .limit(limit)
        .all()
    )
```

- [ ] **Step 3: Register the router**

Open `backend/app/api/v1/router.py`. Replace its full contents:

```python
from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors, toolkit, activity

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
router.include_router(toolkit.router)
router.include_router(activity.router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/activity.py backend/app/api/v1/activity.py backend/app/api/v1/router.py
git commit -m "feat: add activity log endpoint"
```

---

## Task 2: Backend — Tests

**Files:**
- Create: `backend/tests/test_api_activity.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_activity.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(client_id, archived=False):
    m = MagicMock()
    m.id = client_id
    m.archived_at = datetime.utcnow() if archived else None
    return m


def _fake_entry(event_type="scan_completed", note="Test note", day=4):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.event_type = event_type
    m.note = note
    m.created_at = datetime(2026, 6, day, 12, 0)
    return m


def test_list_activity_returns_entries_newest_first():
    """Two entries returned in the order the mock provides (newest first)."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    newer = _fake_entry("toolkit_generated", "Toolkit generated", day=4)
    older = _fake_entry("scan_completed", "Scan completed", day=3)

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = [newer, older]

    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["event_type"] == "toolkit_generated"
    assert data[1]["event_type"] == "scan_completed"


def test_list_activity_returns_empty_list_when_no_entries():
    app, get_db = _make_app()
    client_id = uuid.uuid4()

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = []

    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_activity_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/activity")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_activity_archived_client_returns_404():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id, archived=True)
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/activity")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_activity_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/activity")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
cd backend
pytest tests/test_api_activity.py -v
```

Expected output:
```
test_list_activity_returns_entries_newest_first PASSED
test_list_activity_returns_empty_list_when_no_entries PASSED
test_list_activity_client_not_found_returns_404 PASSED
test_list_activity_archived_client_returns_404 PASSED
test_list_activity_requires_auth PASSED
```

- [ ] **Step 3: Run full test suite — expect all pass**

```bash
cd backend
pytest tests/ -v
```

Expected: all existing tests PASS in addition to the 5 new ones.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_api_activity.py
git commit -m "test: add activity log endpoint tests"
```

---

## Task 3: Backend — Instrument Event Logging

**Files:**
- Modify: `backend/app/api/v1/clients.py`
- Modify: `backend/app/api/v1/toolkit.py`
- Modify: `backend/app/services/scan_service.py`

### 3a: Log client_created in clients.py

- [ ] **Step 1: Add ActivityLog import to clients.py**

Open `backend/app/api/v1/clients.py`. The current imports end with:

```python
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem
from app.schemas.geo_score import GeoScoreResponse
```

Replace those two lines with:

```python
from app.models.activity_log import ActivityLog
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem
from app.schemas.geo_score import GeoScoreResponse
```

- [ ] **Step 2: Add ActivityLog write in create_client**

The current `create_client` function body:

```python
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
```

Replace with:

```python
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    db.add(ActivityLog(
        client_id=c.id,
        event_type="client_created",
        note=f"Client '{c.name}' added to SeenBy.",
    ))
    db.commit()
    return c
```

### 3b: Log toolkit events in toolkit.py

- [ ] **Step 3: Replace the full toolkit.py**

Replace `backend/app/api/v1/toolkit.py` with:

```python
import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.activity_log import ActivityLog
from app.models.toolkit_files import ToolkitFiles
from app.services.toolkit_service import generate_toolkit_files
from app.services.verification_crawler import verify_all
from app.schemas.toolkit import ToolkitFilesResponse, VerificationResult

router = APIRouter(prefix="/clients/{client_id}/toolkit", tags=["toolkit"])


@router.post(
    "/generate",
    response_model=ToolkitFilesResponse,
    dependencies=[Depends(require_api_key)],
)
def generate(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    files_content = generate_toolkit_files(client)

    existing = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if existing:
        existing.llms_txt = files_content["llms_txt"]
        existing.schema_json = files_content["schema_json"]
        existing.robots_txt = files_content["robots_txt"]
        existing.generated_at = datetime.now(UTC)
        existing.llms_verified = False
        existing.schema_verified = False
        existing.robots_verified = False
        existing.verified_at = None
        db.add(ActivityLog(
            client_id=client_id,
            event_type="toolkit_generated",
            note="AI Readiness Toolkit files regenerated (llms.txt, schema.json, robots.txt).",
        ))
        db.commit()
        db.refresh(existing)
        return existing

    tf = ToolkitFiles(client_id=client_id, **files_content)
    db.add(tf)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_generated",
        note="AI Readiness Toolkit files generated (llms.txt, schema.json, robots.txt).",
    ))
    db.commit()
    db.refresh(tf)
    return tf


@router.get(
    "/files",
    response_model=ToolkitFilesResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_files(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()


@router.post(
    "/verify",
    response_model=VerificationResult,
    dependencies=[Depends(require_api_key)],
)
def verify(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    tf = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if not tf:
        raise HTTPException(status_code=404, detail="No toolkit files generated yet")

    results = verify_all(client.website)

    tf.llms_verified = results["llms_verified"]
    tf.schema_verified = results["schema_verified"]
    tf.robots_verified = results["robots_verified"]
    if any(results.values()):
        tf.verified_at = datetime.now(UTC)

    client.technical_foundations_verified = results["llms_verified"]
    client.structured_data_verified = results["schema_verified"]

    verified_names = ", ".join(
        name
        for name, ok in [
            ("llms.txt", results["llms_verified"]),
            ("schema.json", results["schema_verified"]),
            ("robots.txt", results["robots_verified"]),
        ]
        if ok
    ) or "none"
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_verified",
        note=f"Toolkit verification run. Files verified: {verified_names}.",
    ))
    db.commit()

    return VerificationResult(
        llms_verified=results["llms_verified"],
        schema_verified=results["schema_verified"],
        robots_verified=results["robots_verified"],
        technical_foundations_updated=client.technical_foundations_verified,
        structured_data_updated=client.structured_data_verified,
    )


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
```

### 3c: Log scan_failed in scan_service.py

- [ ] **Step 4: Update the except branch in scan_service.py**

Open `backend/app/services/scan_service.py`. Find the except block (currently lines 107–110):

```python
    except Exception as exc:
        scan.status = "failed"
        db.commit()
        logger.error("scan_failed", scan_id=str(scan_id), error=str(exc))
```

Replace with:

```python
    except Exception as exc:
        scan.status = "failed"
        db.add(ActivityLog(
            client_id=scan.client_id,
            event_type="scan_failed",
            note=f"Scan failed: {str(exc)[:200]}",
        ))
        db.commit()
        logger.error("scan_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 5: Run full test suite — all pass**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests PASS (no new tests needed — instrumentation is a write-only side effect that doesn't change endpoint responses).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/clients.py backend/app/api/v1/toolkit.py backend/app/services/scan_service.py
git commit -m "feat: instrument activity log on client create, toolkit generate/verify, scan fail"
```

---

## Task 4: Frontend — Types + API Function + Page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/clients/[id]/activity/page.tsx`

- [ ] **Step 1: Append ActivityLogEntry type to index.ts**

Open `frontend/src/types/index.ts`. The file currently ends after `CompetitorIntelligenceResponse`. Append:

```typescript
export interface ActivityLogEntry {
  id: string
  event_type: string
  note: string
  created_at: string
}
```

- [ ] **Step 2: Add ActivityLogEntry to api.ts import and add getActivityLog function**

Open `frontend/src/lib/api.ts`. Replace the existing import line at the top:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse } from "@/types"
```

with:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry } from "@/types"
```

Then append after the `getCompetitorIntelligence` function and before the `// ── Toolkit` comment:

```typescript
export function getActivityLog(clientId: string, limit = 50): Promise<ActivityLogEntry[]> {
  return apiFetch<ActivityLogEntry[]>(
    `/api/v1/clients/${clientId}/activity?limit=${limit}`,
  )
}
```

- [ ] **Step 3: Replace the placeholder activity page**

Replace the full contents of `frontend/src/app/clients/[id]/activity/page.tsx` with:

```tsx
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus } from "lucide-react"
import { getActivityLog } from "@/lib/api"
import type { ActivityLogEntry } from "@/types"

interface Props {
  params: Promise<{ id: string }>
}

const EVENT_LABELS: Record<string, string> = {
  scan_completed: "Scan completed",
  scan_failed: "Scan failed",
  toolkit_generated: "Toolkit generated",
  toolkit_verified: "Toolkit files verified",
  client_created: "Client onboarded",
}

function EventIcon({ type }: { type: string }) {
  const cls = "h-4 w-4 shrink-0 mt-0.5"
  switch (type) {
    case "scan_completed":
      return <CheckCircle className={`${cls} text-green-500`} />
    case "scan_failed":
      return <XCircle className={`${cls} text-red-500`} />
    case "toolkit_generated":
      return <Wrench className={`${cls} text-blue-500`} />
    case "toolkit_verified":
      return <ShieldCheck className={`${cls} text-purple-500`} />
    case "client_created":
      return <UserPlus className={`${cls} text-muted-foreground`} />
    default:
      return <Activity className={`${cls} text-muted-foreground`} />
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default async function ActivityPage({ params }: Props) {
  const { id } = await params

  let entries: ActivityLogEntry[] = []
  try {
    entries = await getActivityLog(id)
  } catch {
    // backend down — fall through to empty state
  }

  if (entries.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">No activity yet</p>
        <p className="text-sm mt-1">
          Activity is recorded when you run scans, generate toolkit files, or verify your implementation.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      <p className="text-sm text-muted-foreground px-4 mb-3">
        Showing the last {entries.length} event{entries.length !== 1 ? "s" : ""}, newest first.
      </p>
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-start gap-3 rounded-lg px-4 py-3 hover:bg-muted/30 transition-colors"
        >
          <EventIcon type={entry.event_type} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium leading-none">
              {EVENT_LABELS[entry.event_type] ?? entry.event_type}
            </p>
            <p className="text-sm text-muted-foreground mt-1">{entry.note}</p>
          </div>
          <p className="text-xs text-muted-foreground shrink-0 mt-0.5 tabular-nums">
            {formatDate(entry.created_at)}
          </p>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Start dev server and manually verify**

```bash
cd frontend
npm run dev
```

Navigate to `/clients/{id}/activity` and confirm each state:

1. **No activity** — "No activity yet" dashed border empty state with explanation text.
2. **With activity** — list of entries, newest at top. Each row: colored icon left, label + note middle, formatted date right. Hovering a row shows light muted background.
3. **Event labels**: `scan_completed` → "Scan completed" with green check icon; `scan_failed` → "Scan failed" with red X icon; `toolkit_generated` → "Toolkit generated" with blue wrench icon; `toolkit_verified` → "Toolkit files verified" with purple shield icon; `client_created` → "Client onboarded" with muted user+ icon.
4. **Count line**: "Showing the last N events, newest first." above the list.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts "frontend/src/app/clients/[id]/activity/page.tsx"
git commit -m "feat: build activity log page"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Activity page replaces placeholder | Task 4 (full page.tsx rewrite) |
| Newest events first | Task 1 (`order_by(desc(ActivityLog.created_at))`) |
| Scan completed events logged | Already in `scan_service.py` (pre-existing) |
| Scan failed events logged | Task 3 (except branch in scan_service.py) |
| Toolkit generate events logged | Task 3 (toolkit.py generate endpoint) |
| Toolkit verify events logged | Task 3 (toolkit.py verify endpoint) |
| Client onboarded events logged | Task 3 (clients.py create_client) |
| 404 for missing / archived client | Task 1 (endpoint checks `archived_at`) |
| 401 without API key | Task 1 (route has `dependencies=[Depends(require_api_key)]`) |
| Empty state | Task 4 (dashed border empty state) |
| Human-readable labels not raw event_type | Task 4 (`EVENT_LABELS` map) |
| Correct language ("Toolkit generated" not "Citation generated") | Task 4 (event labels follow CLAUDE.md) |

### Placeholder Scan

No TBD / TODO / "implement later" found.

### Type Consistency

- `ActivityLogEntry` Pydantic schema fields (`id`, `event_type`, `note`, `created_at`) match `ActivityLog` model ✓
- `ActivityLogEntry` TypeScript interface fields match Pydantic schema ✓
- `getActivityLog` return type `ActivityLogEntry[]` is imported into `api.ts` ✓
- `api.ts` import line includes `ActivityLogEntry` ✓
- `activity.py` router imports `ActivityLog` from `app.models.activity_log` ✓
- `toolkit.py` imports `ActivityLog` from `app.models.activity_log` ✓
- `clients.py` imports `ActivityLog` from `app.models.activity_log` ✓
- `scan_service.py` already imports `ActivityLog` from `app.models.activity_log` (line 14) ✓
