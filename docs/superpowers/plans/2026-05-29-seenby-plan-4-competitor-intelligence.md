# SeenBy Plan 4: Competitor Intelligence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Competitor Intelligence page — a backend endpoint that computes each competitor's AI visibility score from the latest scan's stored query results, and a frontend page that shows competitor scores vs the client's own score with a clear "winning" flag where competitors are ahead.

**Architecture:** No new DB models or migrations needed — all data already lives in `scan_query_results` (competitor rows have `competitor_id` set, client rows have `competitor_id = NULL`). The backend adds three Pydantic schemas and one `GET /intelligence` route to the existing competitors router, computing scores in Python by grouping already-stored rows. The frontend replaces the placeholder `page.tsx` with a pure async server component (read-only display, no client-side state) that renders competitor cards with per-category query breakdowns.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Pydantic v2 · Next.js 15 · TypeScript · shadcn/ui

---

## File Map

```
backend/
├── app/
│   ├── schemas/
│   │   └── competitor.py                        MODIFY: append 3 new schemas
│   └── api/v1/
│       └── competitors.py                       MODIFY: add imports + GET /intelligence route
└── tests/
    └── test_competitor_intelligence.py          CREATE

frontend/
└── src/
    ├── types/
    │   └── index.ts                             MODIFY: append 3 new types
    ├── lib/
    │   └── api.ts                               MODIFY: add getCompetitorIntelligence
    └── app/clients/[id]/competitors/
        └── page.tsx                             MODIFY: replace placeholder
```

---

## Task 1: Backend — Schemas

**Files:**
- Modify: `backend/app/schemas/competitor.py`

- [ ] **Step 1: Append three schemas**

Open `backend/app/schemas/competitor.py`. The file currently ends after `CompetitorResponse`. Append:

```python
class CompetitorQueryBreakdown(BaseModel):
    category: str
    query_text: str
    brand_detected: bool


class CompetitorScore(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None = None
    ai_citability: float
    queries: list[CompetitorQueryBreakdown]
    is_winning: bool


class CompetitorIntelligenceResponse(BaseModel):
    client_ai_citability: float | None
    competitors: list[CompetitorScore]
    last_scan_at: str | None
```

No imports need changing — `uuid` and `BaseModel` are already imported.

---

## Task 2: Backend — Intelligence Endpoint

**Files:**
- Modify: `backend/app/api/v1/competitors.py`

- [ ] **Step 1: Replace the full file**

The `/intelligence` route must be registered **before** `/{competitor_id}` to avoid FastAPI treating `"intelligence"` as a UUID param. Replace the full contents of `backend/app/api/v1/competitors.py` with:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.core.constants import MAX_COMPETITORS
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorResponse,
    CompetitorIntelligenceResponse,
    CompetitorScore,
    CompetitorQueryBreakdown,
)

router = APIRouter(prefix="/clients/{client_id}/competitors", tags=["competitors"])


@router.get(
    "/intelligence",
    response_model=CompetitorIntelligenceResponse,
    dependencies=[Depends(require_api_key)],
)
def get_intelligence(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)

    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    if not latest_scan:
        return CompetitorIntelligenceResponse(
            client_ai_citability=None,
            competitors=[
                CompetitorScore(
                    id=c.id,
                    name=c.name,
                    website=c.website,
                    ai_citability=0.0,
                    queries=[],
                    is_winning=False,
                )
                for c in competitors
            ],
            last_scan_at=None,
        )

    all_results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == latest_scan.id)
        .all()
    )

    client_results = [r for r in all_results if r.competitor_id is None]
    client_citability = (
        round(sum(1 for r in client_results if r.brand_detected) / len(client_results) * 100, 1)
        if client_results
        else 0.0
    )

    competitor_scores = []
    for comp in competitors:
        comp_results = [r for r in all_results if r.competitor_id == comp.id]
        comp_citability = (
            round(sum(1 for r in comp_results if r.brand_detected) / len(comp_results) * 100, 1)
            if comp_results
            else 0.0
        )
        competitor_scores.append(
            CompetitorScore(
                id=comp.id,
                name=comp.name,
                website=comp.website,
                ai_citability=comp_citability,
                queries=[
                    CompetitorQueryBreakdown(
                        category=r.category,
                        query_text=r.query_text,
                        brand_detected=r.brand_detected,
                    )
                    for r in comp_results
                ],
                is_winning=comp_citability > client_citability,
            )
        )

    return CompetitorIntelligenceResponse(
        client_ai_citability=client_citability,
        competitors=competitor_scores,
        last_scan_at=latest_scan.completed_at.isoformat() if latest_scan.completed_at else None,
    )


@router.get(
    "",
    response_model=list[CompetitorResponse],
    dependencies=[Depends(require_api_key)],
)
def list_competitors(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return db.query(Competitor).filter(Competitor.client_id == client_id).all()


@router.post(
    "",
    response_model=CompetitorResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def add_competitor(
    client_id: uuid.UUID,
    body: CompetitorCreate,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    count = db.query(Competitor).filter(Competitor.client_id == client_id).count()
    if count >= MAX_COMPETITORS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_COMPETITORS} competitors per client",
        )
    comp = Competitor(client_id=client_id, **body.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.delete(
    "/{competitor_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_competitor(
    client_id: uuid.UUID,
    competitor_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    comp = (
        db.query(Competitor)
        .filter(Competitor.id == competitor_id, Competitor.client_id == client_id)
        .first()
    )
    if comp:
        db.delete(comp)
        db.commit()


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
```

---

## Task 3: Backend — Tests

**Files:**
- Create: `backend/tests/test_competitor_intelligence.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_competitor_intelligence.py
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


def _fake_client(client_id):
    m = MagicMock()
    m.id = client_id
    m.archived_at = None
    return m


def _fake_competitor(comp_id, client_id, name="RivalCo"):
    m = MagicMock()
    m.id = comp_id
    m.client_id = client_id
    m.name = name
    m.website = f"https://{name.lower()}.com"
    return m


def _fake_scan(scan_id, client_id):
    m = MagicMock()
    m.id = scan_id
    m.client_id = client_id
    m.status = "completed"
    m.completed_at = datetime(2026, 5, 29, 12, 0)
    return m


def _fake_result(scan_id, competitor_id=None, category="brand", detected=True):
    m = MagicMock()
    m.scan_id = scan_id
    m.competitor_id = competitor_id
    m.category = category
    m.query_text = f"Test {category} query"
    m.brand_detected = detected
    return m


def _build_mock_db(client, scan, all_results, competitors):
    from app.models.scan import Scan as ScanModel
    from app.models.scan_query_result import ScanQueryResult as SQR
    from app.models.competitor import Competitor as CompModel

    scan_mock = MagicMock()
    scan_mock.filter.return_value.order_by.return_value.first.return_value = scan

    result_mock = MagicMock()
    result_mock.filter.return_value.all.return_value = all_results

    comp_mock = MagicMock()
    comp_mock.filter.return_value.all.return_value = competitors

    def query_side_effect(model):
        if model is ScanModel:
            return scan_mock
        if model is SQR:
            return result_mock
        if model is CompModel:
            return comp_mock
        return MagicMock()

    mock_db = MagicMock()
    mock_db.get.return_value = client
    mock_db.query.side_effect = query_side_effect
    return mock_db


def test_intelligence_no_scan_returns_null_citability():
    """No completed scan → client_ai_citability is null, competitors listed with 0%."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=None,
        all_results=[],
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] is None
    assert data["last_scan_at"] is None
    assert len(data["competitors"]) == 1
    assert data["competitors"][0]["ai_citability"] == 0.0
    assert data["competitors"][0]["is_winning"] is False


def test_intelligence_competitor_winning():
    """Competitor detected in 3/4 queries (75%), client in 1/4 (25%) → is_winning True."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    client_results = [
        _fake_result(scan_id, None, "brand", True),
        _fake_result(scan_id, None, "comparison", False),
        _fake_result(scan_id, None, "recommendation", False),
        _fake_result(scan_id, None, "local", False),
    ]
    comp_results = [
        _fake_result(scan_id, comp_id, "brand", True),
        _fake_result(scan_id, comp_id, "comparison", True),
        _fake_result(scan_id, comp_id, "recommendation", True),
        _fake_result(scan_id, comp_id, "local", False),
    ]
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=_fake_scan(scan_id, client_id),
        all_results=client_results + comp_results,
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] == 25.0
    comp = data["competitors"][0]
    assert comp["ai_citability"] == 75.0
    assert comp["is_winning"] is True
    assert len(comp["queries"]) == 4


def test_intelligence_competitor_losing():
    """Client at 100%, competitor at 50% → is_winning False."""
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    client_results = [
        _fake_result(scan_id, None, cat, True)
        for cat in ["brand", "comparison", "recommendation", "local"]
    ]
    comp_results = [
        _fake_result(scan_id, comp_id, "brand", True),
        _fake_result(scan_id, comp_id, "comparison", True),
        _fake_result(scan_id, comp_id, "recommendation", False),
        _fake_result(scan_id, comp_id, "local", False),
    ]
    mock_db = _build_mock_db(
        client=_fake_client(client_id),
        scan=_fake_scan(scan_id, client_id),
        all_results=client_results + comp_results,
        competitors=[_fake_competitor(comp_id, client_id)],
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/intelligence")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["client_ai_citability"] == 100.0
    assert data["competitors"][0]["is_winning"] is False
    assert data["competitors"][0]["ai_citability"] == 50.0


def test_intelligence_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/intelligence")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_intelligence_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/intelligence")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
pytest tests/test_competitor_intelligence.py -v
```

Expected: all 5 tests FAIL (routes don't exist yet — run this BEFORE Task 2 if doing TDD strictly; if you've already done Task 2, the tests should pass now).

- [ ] **Step 3: Run full backend test suite — expect all pass**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests PASS including the 5 new ones.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/competitor.py backend/app/api/v1/competitors.py backend/tests/test_competitor_intelligence.py
git commit -m "feat: add competitor intelligence endpoint"
```

---

## Task 4: Frontend — Types + API Function + Page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/clients/[id]/competitors/page.tsx`

- [ ] **Step 1: Append types to index.ts**

Open `frontend/src/types/index.ts`. Append after the `VerificationResult` interface:

```typescript
export interface CompetitorQueryBreakdown {
  category: string
  query_text: string
  brand_detected: boolean
}

export interface CompetitorScore {
  id: string
  name: string
  website: string | null
  ai_citability: number
  queries: CompetitorQueryBreakdown[]
  is_winning: boolean
}

export interface CompetitorIntelligenceResponse {
  client_ai_citability: number | null
  competitors: CompetitorScore[]
  last_scan_at: string | null
}
```

- [ ] **Step 2: Add API function to api.ts**

Open `frontend/src/lib/api.ts`. Update the import at the top:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse } from "@/types"
```

Then append after the `deleteCompetitor` function (before the Toolkit section comment):

```typescript
export function getCompetitorIntelligence(clientId: string): Promise<CompetitorIntelligenceResponse> {
  return apiFetch<CompetitorIntelligenceResponse>(
    `/api/v1/clients/${clientId}/competitors/intelligence`,
  )
}
```

- [ ] **Step 3: Replace placeholder page.tsx**

Replace the full contents of `frontend/src/app/clients/[id]/competitors/page.tsx` with:

```tsx
import Link from "next/link"
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { getCompetitorIntelligence } from "@/lib/api"

interface Props {
  params: Promise<{ id: string }>
}

const CATEGORY_LABELS: Record<string, string> = {
  brand: "Brand",
  comparison: "Comparison",
  recommendation: "Recommendation",
  local: "Local",
}

export default async function CompetitorsPage({ params }: Props) {
  const { id } = await params

  let data = null
  try {
    data = await getCompetitorIntelligence(id)
  } catch {
    // backend down — show error state
  }

  if (!data) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">Unable to load competitor data</p>
        <p className="text-sm mt-1">Check that the backend is running and try again.</p>
      </div>
    )
  }

  if (data.competitors.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
        <p className="font-medium">No competitors added yet</p>
        <p className="text-sm mt-1">
          Add up to 5 competitors in{" "}
          <Link href={`/clients/${id}/settings`} className="underline underline-offset-4">
            settings
          </Link>{" "}
          to start tracking their visibility.
        </p>
      </div>
    )
  }

  const winningCount = data.competitors.filter((c) => c.is_winning).length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">Competitor Intelligence</h2>
          {data.last_scan_at && (
            <p className="text-sm text-muted-foreground mt-1">
              Based on scan from{" "}
              {new Date(data.last_scan_at).toLocaleDateString("en-MY", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
          )}
        </div>
        {winningCount > 0 && (
          <Badge
            variant="outline"
            className="gap-1.5 text-amber-700 border-amber-300 bg-amber-50"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            {winningCount} competitor{winningCount > 1 ? "s" : ""} winning
          </Badge>
        )}
      </div>

      {/* No scan yet */}
      {data.client_ai_citability === null && (
        <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
          <p className="font-medium">Run your first scan to see competitor intelligence</p>
          <p className="text-sm mt-1">
            Go to{" "}
            <Link href={`/clients/${id}/scan`} className="underline underline-offset-4">
              Scan &amp; Visibility
            </Link>{" "}
            and trigger a scan.
          </p>
        </div>
      )}

      {/* Client score summary */}
      {data.client_ai_citability !== null && (
        <div className="rounded-lg border px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Your AI visibility</p>
            <p className="text-2xl font-bold tabular-nums">
              {data.client_ai_citability.toFixed(0)}
              <span className="text-base font-normal text-muted-foreground">%</span>
            </p>
          </div>
          <p className="text-sm text-muted-foreground">visibility frequency</p>
        </div>
      )}

      {/* Competitor cards */}
      <div className="space-y-4">
        {data.competitors.map((comp) => (
          <div key={comp.id} className="rounded-lg border overflow-hidden">
            {/* Card header */}
            <div className="flex items-start justify-between px-5 py-4 bg-muted/20">
              <div>
                <p className="font-semibold">{comp.name}</p>
                {comp.website && (
                  <p className="text-xs text-muted-foreground mt-0.5">{comp.website}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-xl font-bold tabular-nums">
                    {comp.ai_citability.toFixed(0)}
                    <span className="text-sm font-normal text-muted-foreground">%</span>
                  </p>
                  <p className="text-xs text-muted-foreground">visibility frequency</p>
                </div>
                {comp.is_winning ? (
                  <Badge className="bg-amber-100 text-amber-800 border-amber-200 gap-1 shrink-0">
                    <AlertTriangle className="h-3 w-3" />
                    Your competitors are winning here
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-muted-foreground gap-1 shrink-0">
                    Behind you
                  </Badge>
                )}
              </div>
            </div>

            {/* Query breakdown */}
            {comp.queries.length > 0 ? (
              <div className="divide-y">
                {comp.queries.map((q, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between px-5 py-3 text-sm"
                  >
                    <div className="flex items-center gap-3">
                      {q.brand_detected ? (
                        <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                      ) : (
                        <XCircle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                      )}
                      <span className="text-muted-foreground font-medium">
                        {CATEGORY_LABELS[q.category] ?? q.category}
                      </span>
                    </div>
                    <span
                      className={
                        q.brand_detected
                          ? "text-green-700 font-medium"
                          : "text-muted-foreground"
                      }
                    >
                      {q.brand_detected ? "Seen by AI" : "Not yet seen by AI"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-5 py-4 text-sm text-muted-foreground">
                No scan data for this competitor yet. Run a scan to see their results.
              </div>
            )}
          </div>
        ))}
      </div>
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

- [ ] **Step 5: Start dev server and manually test**

```bash
cd frontend
npm run dev
```

Navigate to `/clients/{id}/competitors` and check each state:

1. **No competitors added** — "No competitors added yet" with link to settings
2. **Competitors added, no scan** — competitor cards show 0% with no query breakdown; "Run your first scan" notice appears
3. **After a scan** — competitor cards show real percentages, 4-row query breakdown per card
4. **Winning competitor** — amber "Your competitors are winning here" badge on card + header count badge
5. **Trailing competitor** — "Behind you" outline badge

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts "frontend/src/app/clients/[id]/competitors/page.tsx"
git commit -m "feat: build competitor intelligence page"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Competitor scores visible | Task 2 (endpoint computes competitor AI citability) + Task 4 (score % per card) |
| Client score vs competitor comparison | Task 2 (`is_winning` field) + Task 4 (client summary bar + badges) |
| "Your competitors are winning here" label | Task 4 (exact phrase on winning badge) |
| "Seen by AI / Not yet seen by AI" per query | Task 4 (query breakdown rows) |
| "visibility frequency" not "citation rate" | Task 4 (all score labels use this phrase) |
| No scan yet state | Task 4 ("Run your first scan" dashed box with scan link) |
| No competitors state | Task 4 ("No competitors added yet" with link to settings) |
| Overtake flag correct | Task 2 (`is_winning = comp_citability > client_citability`) + Task 4 (amber badge) |
| Competitor added but no scan results yet | Task 2 (returns 0% + empty queries) + Task 4 ("No scan data yet" message in card) |

### Placeholder Scan

No TBD/TODO/similar found in the plan.

### Type Consistency

- `CompetitorQueryBreakdown` fields (`category`, `query_text`, `brand_detected`) match between `competitor.py` schema and `index.ts` ✓
- `CompetitorScore` fields (`id`, `name`, `website`, `ai_citability`, `queries`, `is_winning`) match between schema and type ✓
- `CompetitorIntelligenceResponse` fields (`client_ai_citability`, `competitors`, `last_scan_at`) match between schema and type ✓
- `getCompetitorIntelligence` return type `CompetitorIntelligenceResponse` is imported into `api.ts` ✓
- `competitors.py` imports `Scan` from `app.models.scan` — model exists ✓
- `competitors.py` imports `ScanQueryResult` from `app.models.scan_query_result` — model exists ✓
- `CompetitorQueryBreakdown` and `CompetitorScore` imported in `competitors.py` before use in endpoint ✓
- Test helper `_build_mock_db` imports `Scan`, `ScanQueryResult`, `Competitor` from their correct module paths ✓
