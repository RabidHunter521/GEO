# SeenBy Plan 2: Admin Panel + Onboarding Wizard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js 15 admin panel with Auth.js v5 credentials login, an onboarding wizard that creates clients in 3 steps, and all client route shells — while adding FastAPI CRUD endpoints for clients and competitors.

**Architecture:** Backend gains CORS middleware, a Bearer API-key auth dependency, and CRUD routes for clients + competitors. The frontend is a new `frontend/` Next.js 15 app. Auth.js v5 handles the single-admin credentials login (username + password from env vars). All FastAPI calls are made server-side — in server components and server actions — using `ADMIN_API_KEY` from env vars, which is never exposed to the browser. The 3-step onboarding wizard is a client component that calls server actions for mutations. Steps 2 and 3 are optional at wizard time; the settings page handles them later.

**Tech Stack:** Next.js 15.3 · React 19 · TypeScript · Tailwind CSS 3 · shadcn/ui · Auth.js v5 (`next-auth@beta`) · FastAPI · SQLAlchemy 2 · pytest

---

## File Map

```
backend/
├── app/
│   ├── main.py                        MODIFY: add CORSMiddleware
│   ├── core/
│   │   ├── config.py                  MODIFY: add ADMIN_API_KEY, ALLOWED_ORIGINS
│   │   └── auth.py                    CREATE: require_api_key FastAPI dependency
│   ├── api/v1/
│   │   ├── router.py                  MODIFY: register clients + competitors routers
│   │   ├── scans.py                   MODIFY: protect with require_api_key
│   │   ├── clients.py                 CREATE: list, create, get, update, latest-score
│   │   └── competitors.py             CREATE: list, add, delete (max 5)
│   └── schemas/
│       ├── client.py                  CREATE: ClientCreate, ClientUpdate, ClientResponse, ClientListItem
│       ├── competitor.py              CREATE: CompetitorCreate, CompetitorResponse
│       └── geo_score.py               CREATE: GeoScoreResponse
└── tests/
    ├── test_api_clients.py            CREATE
    └── test_api_competitors.py        CREATE

frontend/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── components.json
├── auth.ts                            Auth.js v5 config
├── middleware.ts                      route protection
├── .env.local.example
└── src/
    ├── app/
    │   ├── globals.css
    │   ├── layout.tsx                 root HTML shell
    │   ├── page.tsx                   redirect → /clients
    │   ├── api/auth/[...nextauth]/
    │   │   └── route.ts               Auth.js route handler
    │   ├── auth/login/
    │   │   └── page.tsx               login form
    │   └── clients/
    │       ├── layout.tsx             AdminShell wrapper
    │       ├── page.tsx               clients list (server component)
    │       ├── actions.ts             createClient, addCompetitor, deleteCompetitor
    │       └── [id]/
    │           ├── layout.tsx         fetches client, passes name to header
    │           ├── page.tsx           score overview
    │           ├── scan/page.tsx      placeholder
    │           ├── competitors/page.tsx  placeholder
    │           ├── toolkit/page.tsx      placeholder
    │           ├── reports/page.tsx      placeholder
    │           ├── activity/page.tsx     placeholder
    │           └── settings/
    │               ├── page.tsx       edit client form
    │               └── actions.ts     updateClient
    ├── components/
    │   ├── layout/
    │   │   └── Sidebar.tsx            "use client", usePathname for context nav
    │   ├── clients/
    │   │   ├── ClientCard.tsx
    │   │   ├── AddClientButton.tsx    "use client", opens wizard dialog
    │   │   └── OnboardingWizard.tsx   "use client", 3-step wizard
    │   └── score/
    │       └── ScoreBadge.tsx
    ├── lib/
    │   ├── api.ts                     server-side FastAPI client (never imported by client components)
    │   ├── score-utils.ts             getScoreBand helper
    │   └── utils.ts                   cn() from shadcn
    └── types/
        └── index.ts
```

---

## Task 1: Backend — CORS + API Key Auth

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/auth.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/scans.py`

- [ ] **Step 1: Add ADMIN_API_KEY and ALLOWED_ORIGINS to config.py**

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: str
    ADMIN_JWT_SECRET: str
    ADMIN_API_KEY: str
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
```

- [ ] **Step 2: Create auth.py dependency**

```python
# backend/app/core/auth.py
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import settings

_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def require_api_key(authorization: str | None = Security(_api_key_header)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
```

- [ ] **Step 3: Add CORS to main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router
from app.core.config import settings

app = FastAPI(title="SeenBy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Protect existing scan endpoints**

```python
# backend/app/api/v1/scans.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.scan import Scan
from app.schemas.scan import TriggerScanRequest, ScanResponse

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post(
    "/",
    response_model=ScanResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def trigger_scan(payload: TriggerScanRequest, db: Session = Depends(get_db)):
    from workers.tasks.scan_tasks import execute_scan

    scan = Scan(client_id=payload.client_id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    execute_scan.delay(str(scan.id))
    return scan


@router.get(
    "/{scan_id}",
    response_model=ScanResponse,
    dependencies=[Depends(require_api_key)],
)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
```

- [ ] **Step 5: Add ADMIN_API_KEY to backend/.env**

Open `backend/.env` and add:
```
ADMIN_API_KEY=your-strong-random-key-here
ALLOWED_ORIGINS=http://localhost:3000
```

- [ ] **Step 6: Run existing tests to confirm nothing broke**

```bash
cd backend
pytest tests/ -v
```

Expected: all existing tests pass. Note: the scan tests use `app.dependency_overrides` and mock `get_db` — they will not hit the auth guard because the test for `trigger_scan` calls the endpoint without auth, which will now return 401. Update `test_api_scans.py`'s two non-health tests to include the auth override:

```python
# backend/tests/test_api_scans.py  — update the two endpoint tests
# Add this import at the top:
from app.core.auth import require_api_key

# In test_trigger_scan_returns_202, before creating TestClient:
app.dependency_overrides[require_api_key] = lambda: None

# In test_get_scan_not_found, before creating TestClient:
app.dependency_overrides[require_api_key] = lambda: None
```

Run again: `pytest tests/ -v` — all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/core/auth.py backend/app/main.py backend/app/api/v1/scans.py backend/tests/test_api_scans.py
git commit -m "feat: add CORS middleware and API key auth dependency"
```

---

## Task 2: Backend — Client CRUD API

**Files:**
- Create: `backend/app/schemas/client.py`
- Create: `backend/app/schemas/geo_score.py`
- Create: `backend/app/api/v1/clients.py`
- Create: `backend/tests/test_api_clients.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_api_clients.py
import uuid
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_client(name="Acme Corp"):
    from datetime import datetime
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = name
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = None
    m.target_audience = None
    m.city = None
    m.state = None
    m.contact_email = None
    m.brand_authority_score = 0
    m.content_quality_score = 0
    m.technical_foundations_verified = False
    m.structured_data_verified = False
    m.score_drop_threshold = 35
    m.created_at = datetime(2026, 1, 1)
    m.archived_at = None
    # Make it behave like a dict for model_validate
    m.__class__.__tablename__ = "clients"
    return m


def test_list_clients_returns_empty():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get("/api/v1/clients")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == []


def test_create_client_returns_201():
    app, get_db = _make_app()
    created = _fake_client("TestCo")

    def fake_refresh(obj):
        obj.id = created.id
        obj.name = created.name
        obj.website = created.website
        obj.industry = created.industry
        obj.description = None
        obj.target_audience = None
        obj.city = None
        obj.state = None
        obj.contact_email = None
        obj.brand_authority_score = 0
        obj.content_quality_score = 0
        obj.technical_foundations_verified = False
        obj.structured_data_verified = False
        obj.score_drop_threshold = 35
        from datetime import datetime
        obj.created_at = datetime(2026, 1, 1)
        obj.archived_at = None

    mock_db = MagicMock()
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.post(
        "/api/v1/clients",
        json={"name": "TestCo", "website": "https://test.co", "industry": "SaaS"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["name"] == "TestCo"


def test_get_client_not_found():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_update_client():
    app, get_db = _make_app()
    existing = _fake_client("Old Name")
    existing.city = None

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.patch(
        f"/api/v1/clients/{existing.id}",
        json={"city": "Kuala Lumpur"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200


def test_latest_geo_score_returns_none_when_no_scans():
    app, get_db = _make_app()
    existing = _fake_client()

    mock_db = MagicMock()
    mock_db.get.return_value = existing
    mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)
    response = client.get(f"/api/v1/clients/{existing.id}/geo-score/latest")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() is None


def test_endpoints_require_auth():
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/v1/clients")
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests — expect failure (route not yet defined)**

```bash
cd backend
pytest tests/test_api_clients.py -v
```

Expected: FAIL with `404 Not Found` or `AttributeError` — routes don't exist yet.

- [ ] **Step 3: Create client schemas**

```python
# backend/app/schemas/client.py
import uuid
from datetime import datetime
from pydantic import BaseModel


class ClientCreate(BaseModel):
    name: str
    website: str
    industry: str


class ClientUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    description: str | None = None
    target_audience: str | None = None
    city: str | None = None
    state: str | None = None
    contact_email: str | None = None
    brand_authority_score: int | None = None
    content_quality_score: int | None = None
    score_drop_threshold: int | None = None


class ClientResponse(BaseModel):
    id: uuid.UUID
    name: str
    website: str
    industry: str
    description: str | None = None
    target_audience: str | None = None
    city: str | None = None
    state: str | None = None
    contact_email: str | None = None
    brand_authority_score: int
    content_quality_score: int
    technical_foundations_verified: bool
    structured_data_verified: bool
    score_drop_threshold: int
    created_at: datetime
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClientListItem(ClientResponse):
    latest_overall_score: float | None = None
    last_scan_at: datetime | None = None

    model_config = {"from_attributes": False}
```

- [ ] **Step 4: Create GeoScore schema**

```python
# backend/app/schemas/geo_score.py
import uuid
from datetime import datetime
from pydantic import BaseModel


class GeoScoreResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    scan_id: uuid.UUID
    ai_citability: float
    brand_authority: float
    content_quality: float
    technical_foundations: float
    structured_data: float
    overall_score: float
    computed_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create clients API**

```python
# backend/app/api/v1/clients.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem
from app.schemas.geo_score import GeoScoreResponse

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientListItem], dependencies=[Depends(require_api_key)])
def list_clients(db: Session = Depends(get_db)):
    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None))
        .order_by(desc(Client.created_at))
        .all()
    )
    items = []
    for c in clients:
        latest = (
            db.query(GeoScore)
            .filter(GeoScore.client_id == c.id)
            .order_by(desc(GeoScore.computed_at))
            .first()
        )
        base = ClientResponse.model_validate(c).model_dump()
        items.append(
            ClientListItem(
                **base,
                latest_overall_score=latest.overall_score if latest else None,
                last_scan_at=latest.computed_at if latest else None,
            )
        )
    return items


@router.post(
    "",
    response_model=ClientResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def update_client(client_id: uuid.UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/{client_id}/geo-score/latest",
    response_model=GeoScoreResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_geo_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd backend
pytest tests/test_api_clients.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/client.py backend/app/schemas/geo_score.py backend/app/api/v1/clients.py backend/tests/test_api_clients.py
git commit -m "feat: add client CRUD API endpoints"
```

---

## Task 3: Backend — Competitor CRUD API + Router Update

**Files:**
- Create: `backend/app/schemas/competitor.py`
- Create: `backend/app/api/v1/competitors.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/backend/.env.example`
- Create: `backend/tests/test_api_competitors.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_api_competitors.py
import uuid
from unittest.mock import MagicMock
from fastapi.testclient import TestClient


def _make_app():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    return app, get_db


def _fake_competitor(client_id):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.client_id = client_id
    m.name = "Rival Co"
    m.website = "https://rival.com"
    return m


def _fake_client():
    m = MagicMock()
    m.id = uuid.uuid4()
    return m


def test_list_competitors_empty():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_competitor_returns_201():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    comp = _fake_competitor(client_id)

    def fake_refresh(obj):
        obj.id = comp.id
        obj.client_id = comp.client_id
        obj.name = comp.name
        obj.website = comp.website

    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client()
    mock_db.query.return_value.filter.return_value.count.return_value = 0
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(
        f"/api/v1/clients/{client_id}/competitors",
        json={"name": "Rival Co", "website": "https://rival.com"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 201
    assert resp.json()["name"] == "Rival Co"


def test_add_competitor_rejects_over_limit():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client()
    mock_db.query.return_value.filter.return_value.count.return_value = 5
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(
        f"/api/v1/clients/{client_id}/competitors",
        json={"name": "Extra Co"},
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_delete_competitor_not_found():
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client()
    mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.delete(f"/api/v1/clients/{client_id}/competitors/{uuid.uuid4()}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
pytest tests/test_api_competitors.py -v
```

Expected: FAIL — routes don't exist yet.

- [ ] **Step 3: Create competitor schemas**

```python
# backend/app/schemas/competitor.py
import uuid
from pydantic import BaseModel


class CompetitorCreate(BaseModel):
    name: str
    website: str | None = None


class CompetitorResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    website: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create competitors API**

```python
# backend/app/api/v1/competitors.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.competitor import Competitor
from app.schemas.competitor import CompetitorCreate, CompetitorResponse

MAX_COMPETITORS = 5

router = APIRouter(prefix="/clients/{client_id}/competitors", tags=["competitors"])


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
    comp = (
        db.query(Competitor)
        .filter(Competitor.id == competitor_id, Competitor.client_id == client_id)
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")
    db.delete(comp)
    db.commit()


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
```

- [ ] **Step 5: Register both new routers in router.py**

```python
# backend/app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
```

- [ ] **Step 6: Update .env.example**

```bash
# backend/.env.example  — add these two lines:
ADMIN_API_KEY=replace-with-a-strong-random-secret
ALLOWED_ORIGINS=http://localhost:3000
```

- [ ] **Step 7: Run all backend tests — expect all pass**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/competitor.py backend/app/api/v1/competitors.py backend/app/api/v1/router.py backend/tests/test_api_competitors.py backend/.env.example
git commit -m "feat: add competitor CRUD API, register all routers"
```

---

## Task 4: Frontend Scaffold

**Files:** All frontend config files, globals.css, utils.ts

- [ ] **Step 1: Create frontend directory and package.json**

```bash
mkdir frontend
```

```json
// frontend/package.json
{
  "name": "seenby-admin",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "15.3.2",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "next-auth": "^5.0.0-beta.25",
    "lucide-react": "^0.469.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.6.0",
    "@radix-ui/react-dialog": "^1.1.4",
    "@radix-ui/react-label": "^2.1.1",
    "@radix-ui/react-separator": "^1.1.1",
    "@radix-ui/react-slot": "^1.1.1"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "tailwindcss": "^3.4.17",
    "postcss": "^8",
    "autoprefixer": "^10.0.1",
    "eslint": "^9",
    "eslint-config-next": "15.3.2"
  }
}
```

- [ ] **Step 2: Create next.config.ts**

```typescript
// frontend/next.config.ts
import type { NextConfig } from "next"

const nextConfig: NextConfig = {}

export default nextConfig
```

- [ ] **Step 3: Create tsconfig.json**

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 4: Create tailwind.config.ts and postcss.config.mjs**

```typescript
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
export default config
```

```javascript
// frontend/postcss.config.mjs
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 5: Create components.json (shadcn/ui config)**

```json
// frontend/components.json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/app/globals.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

- [ ] **Step 6: Create src/app/globals.css**

Create the directory `frontend/src/app/` first, then:

```css
/* frontend/src/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

- [ ] **Step 7: Create src/lib/utils.ts**

```typescript
// frontend/src/lib/utils.ts
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 8: Install dependencies**

```bash
cd frontend
npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 9: Install shadcn/ui base components**

```bash
cd frontend
npx shadcn@latest add button card input label badge dialog separator
```

This creates `src/components/ui/{button,card,input,label,badge,dialog,separator}.tsx`.

- [ ] **Step 10: Verify TypeScript compiles**

```bash
cd frontend
npm run typecheck
```

Expected: no errors (may warn about missing `next-env.d.ts` until `npm run dev` is run once — that's fine).

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js 15 frontend with shadcn/ui"
```

---

## Task 5: Frontend — Auth.js v5 + Login Page

**Files:**
- Create: `frontend/auth.ts`
- Create: `frontend/middleware.ts`
- Create: `frontend/src/app/api/auth/[...nextauth]/route.ts`
- Create: `frontend/src/app/auth/login/page.tsx`
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Create auth.ts**

```typescript
// frontend/auth.ts
import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (
          credentials?.username === process.env.ADMIN_USERNAME &&
          credentials?.password === process.env.ADMIN_PASSWORD
        ) {
          return { id: "admin", name: "Admin", email: "admin@seenby.my" }
        }
        return null
      },
    }),
  ],
  pages: {
    signIn: "/auth/login",
  },
  session: {
    strategy: "jwt",
  },
})
```

- [ ] **Step 2: Create middleware.ts**

```typescript
// frontend/middleware.ts
export { auth as default } from "@/auth"

export const config = {
  matcher: [
    "/((?!api/auth|auth|_next/static|_next/image|favicon.ico).*)",
  ],
}
```

- [ ] **Step 3: Create the Auth.js route handler**

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
import { handlers } from "@/auth"

export const { GET, POST } = handlers
```

Wait — this imports from `@/auth` but `auth.ts` is at the root, not inside `src/`. The `@/*` path alias maps to `./src/*`. So the import should be relative or we need to adjust the alias.

Instead, use a relative import:

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
import { handlers } from "../../../../auth"

export const { GET, POST } = handlers
```

- [ ] **Step 4: Create login page**

```tsx
// frontend/src/app/auth/login/page.tsx
"use client"

import { useState } from "react"
import { signIn } from "next-auth/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const data = new FormData(e.currentTarget)
    const result = await signIn("credentials", {
      username: data.get("username") as string,
      password: data.get("password") as string,
      callbackUrl: "/clients",
      redirect: false,
    })
    if (result?.error) {
      setError("Invalid username or password")
      setLoading(false)
    } else if (result?.url) {
      window.location.href = result.url
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/40">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">SeenBy</CardTitle>
          <CardDescription>Admin access only</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 5: Create .env.local.example**

```bash
# frontend/.env.local.example
NEXTAUTH_URL=http://localhost:3000
AUTH_SECRET=replace-with-32-char-random-string

ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-strong-password

# Backend FastAPI URL
API_BASE_URL=http://localhost:8000
# Must match ADMIN_API_KEY in backend/.env
ADMIN_API_KEY=replace-with-same-key-as-backend
```

- [ ] **Step 6: Create .env.local from example**

Copy `.env.local.example` to `.env.local` and fill in real values. Minimum required:
```
AUTH_SECRET=<run: openssl rand -base64 32>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<your password>
API_BASE_URL=http://localhost:8000
ADMIN_API_KEY=<same as backend ADMIN_API_KEY>
```

- [ ] **Step 7: Verify login works**

```bash
cd frontend
npm run dev
```

Visit `http://localhost:3000` — should redirect to `/auth/login`. Enter credentials, should redirect to `/clients` (which will 404 for now — that's fine). Verify the flow works.

- [ ] **Step 8: Commit**

```bash
git add frontend/auth.ts frontend/middleware.ts "frontend/src/app/api/auth/[...nextauth]/route.ts" frontend/src/app/auth/login/page.tsx frontend/.env.local.example
git commit -m "feat: add Auth.js v5 credentials login"
```

---

## Task 6: Frontend — Types, API Client, Score Utils

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/lib/score-utils.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: Create types/index.ts**

```typescript
// frontend/src/types/index.ts

export interface Client {
  id: string
  name: string
  website: string
  industry: string
  description: string | null
  target_audience: string | null
  city: string | null
  state: string | null
  contact_email: string | null
  brand_authority_score: number
  content_quality_score: number
  technical_foundations_verified: boolean
  structured_data_verified: boolean
  score_drop_threshold: number
  created_at: string
  archived_at: string | null
}

export interface ClientListItem extends Client {
  latest_overall_score: number | null
  last_scan_at: string | null
}

export interface Competitor {
  id: string
  client_id: string
  name: string
  website: string | null
}

export interface GeoScore {
  id: string
  client_id: string
  scan_id: string
  ai_citability: number
  brand_authority: number
  content_quality: number
  technical_foundations: number
  structured_data: number
  overall_score: number
  computed_at: string
}

export interface ScoreBand {
  name: "excellent" | "good" | "fair" | "developing" | "low"
  color: "green" | "yellow" | "red"
}
```

- [ ] **Step 2: Create lib/score-utils.ts**

```typescript
// frontend/src/lib/score-utils.ts
import type { ScoreBand } from "@/types"

const SCORE_BANDS: Array<ScoreBand & { min: number; max: number }> = [
  { name: "excellent", min: 80, max: 100, color: "green" },
  { name: "good",      min: 65, max: 79,  color: "green" },
  { name: "fair",      min: 50, max: 64,  color: "yellow" },
  { name: "developing",min: 35, max: 49,  color: "yellow" },
  { name: "low",       min: 0,  max: 34,  color: "red" },
]

export function getScoreBand(score: number): ScoreBand & { min: number; max: number } {
  return (
    SCORE_BANDS.find((b) => score >= b.min && score <= b.max) ?? SCORE_BANDS[4]
  )
}
```

- [ ] **Step 3: Create lib/api.ts**

This file is server-only — it must never be imported by client components. It uses `process.env.ADMIN_API_KEY`.

```typescript
// frontend/src/lib/api.ts
import type { Client, ClientListItem, Competitor, GeoScore } from "@/types"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

function apiHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${process.env.ADMIN_API_KEY}`,
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...apiHeaders(), ...init?.headers },
    cache: "no-store",
  })
  if (!res.ok) {
    throw new Error(`API ${init?.method ?? "GET"} ${path} → ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// Clients
export function getClients(): Promise<ClientListItem[]> {
  return apiFetch<ClientListItem[]>("/api/v1/clients")
}

export function getClient(id: string): Promise<Client> {
  return apiFetch<Client>(`/api/v1/clients/${id}`)
}

export function createClient(
  body: Pick<Client, "name" | "website" | "industry">,
): Promise<Client> {
  return apiFetch<Client>("/api/v1/clients", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function updateClient(
  id: string,
  body: Partial<
    Pick<
      Client,
      | "name"
      | "website"
      | "industry"
      | "description"
      | "target_audience"
      | "city"
      | "state"
      | "contact_email"
      | "brand_authority_score"
      | "content_quality_score"
      | "score_drop_threshold"
    >
  >,
): Promise<Client> {
  return apiFetch<Client>(`/api/v1/clients/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export function getLatestGeoScore(clientId: string): Promise<GeoScore | null> {
  return apiFetch<GeoScore | null>(`/api/v1/clients/${clientId}/geo-score/latest`)
}

// Competitors
export function getCompetitors(clientId: string): Promise<Competitor[]> {
  return apiFetch<Competitor[]>(`/api/v1/clients/${clientId}/competitors`)
}

export function addCompetitor(
  clientId: string,
  body: Pick<Competitor, "name"> & { website?: string },
): Promise<Competitor> {
  return apiFetch<Competitor>(`/api/v1/clients/${clientId}/competitors`, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function deleteCompetitor(
  clientId: string,
  competitorId: string,
): Promise<void> {
  return apiFetch<void>(`/api/v1/clients/${clientId}/competitors/${competitorId}`, {
    method: "DELETE",
  })
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/score-utils.ts frontend/src/lib/api.ts
git commit -m "feat: add frontend types, API client, and score utilities"
```

---

## Task 7: Frontend — Root Layout, Sidebar, Clients Section Layout

**Files:**
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/app/clients/layout.tsx`

- [ ] **Step 1: Create root layout**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "SeenBy Admin",
  description: "AI visibility tracking admin panel",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  )
}
```

- [ ] **Step 2: Create root page — redirect to /clients**

```tsx
// frontend/src/app/page.tsx
import { redirect } from "next/navigation"

export default function RootPage() {
  redirect("/clients")
}
```

- [ ] **Step 3: Create Sidebar component**

The sidebar uses `usePathname` to detect whether we're inside a specific client's pages and show the matching sub-navigation.

```tsx
// frontend/src/components/layout/Sidebar.tsx
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { signOut } from "next-auth/react"
import {
  LayoutDashboard,
  Search,
  BarChart3,
  Wrench,
  FileText,
  Activity,
  Settings,
  Users,
  LogOut,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

const CLIENT_NAV = [
  { href: "",            label: "Overview",               icon: LayoutDashboard },
  { href: "/scan",       label: "Scan & Visibility",      icon: Search },
  { href: "/competitors",label: "Competitor Intelligence", icon: BarChart3 },
  { href: "/toolkit",    label: "AI Readiness Toolkit",   icon: Wrench },
  { href: "/reports",    label: "Reports",                icon: FileText },
  { href: "/activity",   label: "Activity Log",           icon: Activity },
  { href: "/settings",   label: "Settings",               icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const clientId = clientMatch?.[1]

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(href + "/")
  }

  return (
    <aside className="w-60 border-r bg-background flex flex-col h-screen sticky top-0 shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b">
        <span className="font-semibold text-base tracking-tight">SeenBy</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
        <Link
          href="/clients"
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
            isActive("/clients") && !clientId
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
          )}
        >
          <Users className="h-4 w-4" />
          All Clients
        </Link>

        {clientId && (
          <>
            <Separator className="my-2" />
            {CLIENT_NAV.map((item) => {
              const href = `/clients/${clientId}${item.href}`
              const active =
                item.href === ""
                  ? pathname === `/clients/${clientId}`
                  : pathname.startsWith(href)
              return (
                <Link
                  key={item.href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                    active
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </Link>
              )
            })}
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground hover:text-foreground gap-2"
          onClick={() => signOut({ callbackUrl: "/auth/login" })}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: Create clients section layout**

```tsx
// frontend/src/app/clients/layout.tsx
import { Sidebar } from "@/components/layout/Sidebar"

export default function ClientsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/src/app/page.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/app/clients/layout.tsx
git commit -m "feat: add root layout, redirect, sidebar, and clients section layout"
```

---

## Task 8: Frontend — ScoreBadge, ClientCard, Clients List Page

**Files:**
- Create: `frontend/src/components/score/ScoreBadge.tsx`
- Create: `frontend/src/components/clients/ClientCard.tsx`
- Create: `frontend/src/app/clients/page.tsx`
- Create: `frontend/src/app/clients/actions.ts`

- [ ] **Step 1: Create ScoreBadge**

```tsx
// frontend/src/components/score/ScoreBadge.tsx
import { Badge } from "@/components/ui/badge"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

interface Props {
  score: number | null
  className?: string
}

export function ScoreBadge({ score, className }: Props) {
  if (score === null) {
    return (
      <Badge variant="outline" className={cn("text-muted-foreground", className)}>
        —
      </Badge>
    )
  }

  const band = getScoreBand(score)
  const colorClass =
    band.color === "green"
      ? "bg-green-100 text-green-800 border-green-200"
      : band.color === "yellow"
        ? "bg-yellow-100 text-yellow-800 border-yellow-200"
        : "bg-red-100 text-red-800 border-red-200"

  return (
    <Badge
      variant="outline"
      className={cn("font-semibold", colorClass, className)}
    >
      {score.toFixed(0)}
    </Badge>
  )
}
```

- [ ] **Step 2: Create ClientCard**

```tsx
// frontend/src/components/clients/ClientCard.tsx
import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScoreBadge } from "@/components/score/ScoreBadge"
import type { ClientListItem } from "@/types"

interface Props {
  client: ClientListItem
}

export function ClientCard({ client }: Props) {
  const lastScan = client.last_scan_at
    ? new Date(client.last_scan_at).toLocaleDateString("en-MY", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null

  return (
    <Link href={`/clients/${client.id}`} className="block group">
      <Card className="h-full transition-shadow group-hover:shadow-md">
        <CardHeader className="pb-2 flex flex-row items-start justify-between space-y-0">
          <div className="min-w-0">
            <p className="font-semibold truncate">{client.name}</p>
            <p className="text-xs text-muted-foreground truncate">{client.website}</p>
          </div>
          <ScoreBadge score={client.latest_overall_score} className="ml-2 shrink-0" />
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">{client.industry}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {lastScan ? `Last scan ${lastScan}` : "No scans yet"}
          </p>
        </CardContent>
      </Card>
    </Link>
  )
}
```

- [ ] **Step 3: Create clients/actions.ts (server actions)**

```typescript
// frontend/src/app/clients/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import {
  createClient as apiCreateClient,
  addCompetitor as apiAddCompetitor,
  deleteCompetitor as apiDeleteCompetitor,
} from "@/lib/api"

export async function createClientAction(data: {
  name: string
  website: string
  industry: string
}) {
  const client = await apiCreateClient(data)
  revalidatePath("/clients")
  return client
}

export async function addCompetitorAction(
  clientId: string,
  data: { name: string; website?: string },
) {
  const comp = await apiAddCompetitor(clientId, data)
  revalidatePath(`/clients/${clientId}`)
  return comp
}

export async function deleteCompetitorAction(
  clientId: string,
  competitorId: string,
) {
  await apiDeleteCompetitor(clientId, competitorId)
  revalidatePath(`/clients/${clientId}`)
}
```

- [ ] **Step 4: Create clients list page**

```tsx
// frontend/src/app/clients/page.tsx
import { getClients } from "@/lib/api"
import { ClientCard } from "@/components/clients/ClientCard"
import { AddClientButton } from "@/components/clients/AddClientButton"

export default async function ClientsPage() {
  const clients = await getClients()

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Clients</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {clients.length} client{clients.length !== 1 ? "s" : ""}
          </p>
        </div>
        <AddClientButton />
      </div>

      {clients.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">No clients yet</p>
          <p className="text-sm mt-1">Add your first client to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((client) => (
            <ClientCard key={client.id} client={client} />
          ))}
        </div>
      )}
    </div>
  )
}
```

Note: `AddClientButton` is created in Task 9. This page will not compile until then. If you want to verify incrementally, replace `<AddClientButton />` with `<button>Add Client</button>` temporarily.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/score/ScoreBadge.tsx frontend/src/components/clients/ClientCard.tsx frontend/src/app/clients/page.tsx frontend/src/app/clients/actions.ts
git commit -m "feat: add ScoreBadge, ClientCard, clients list page, and server actions"
```

---

## Task 9: Frontend — Onboarding Wizard

**Files:**
- Create: `frontend/src/components/clients/AddClientButton.tsx`
- Create: `frontend/src/components/clients/OnboardingWizard.tsx`

- [ ] **Step 1: Create OnboardingWizard**

The wizard has 3 steps:
- Step 1: Name + website + industry → calls `createClientAction` immediately
- Step 2: Up to 5 competitors (name + website per competitor)
- Step 3: Description + target audience + city + state + contact email

Exiting after Step 1 is allowed — client is already created and scannable.

```tsx
// frontend/src/components/clients/OnboardingWizard.tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  createClientAction,
  addCompetitorAction,
  deleteCompetitorAction,
} from "@/app/clients/actions"
import type { Client, Competitor } from "@/types"

type Step = 1 | 2 | 3

interface Props {
  onClose: () => void
}

export function OnboardingWizard({ onClose }: Props) {
  const router = useRouter()
  const [step, setStep] = useState<Step>(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Step 1 state
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [industry, setIndustry] = useState("")
  const [createdClient, setCreatedClient] = useState<Client | null>(null)

  // Step 2 state
  const [competitors, setCompetitors] = useState<Competitor[]>([])
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")
  const [addingComp, setAddingComp] = useState(false)

  // Step 3 state
  const [description, setDescription] = useState("")
  const [targetAudience, setTargetAudience] = useState("")
  const [city, setCity] = useState("")
  const [state, setState] = useState("")
  const [contactEmail, setContactEmail] = useState("")

  // ── Step 1 ──────────────────────────────────────────────────────────────────
  async function handleStep1(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const client = await createClientAction({ name, website, industry })
      setCreatedClient(client)
      setStep(2)
    } catch {
      setError("Failed to create client. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2 ──────────────────────────────────────────────────────────────────
  async function handleAddCompetitor() {
    if (!createdClient || !compName.trim()) return
    setAddingComp(true)
    setError(null)
    try {
      const comp = await addCompetitorAction(createdClient.id, {
        name: compName.trim(),
        website: compWebsite.trim() || undefined,
      })
      setCompetitors((prev) => [...prev, comp])
      setCompName("")
      setCompWebsite("")
    } catch {
      setError("Failed to add competitor.")
    } finally {
      setAddingComp(false)
    }
  }

  async function handleRemoveCompetitor(id: string) {
    if (!createdClient) return
    try {
      await deleteCompetitorAction(createdClient.id, id)
      setCompetitors((prev) => prev.filter((c) => c.id !== id))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  // ── Step 3 ──────────────────────────────────────────────────────────────────
  async function handleStep3(e: React.FormEvent) {
    e.preventDefault()
    if (!createdClient) return
    setLoading(true)
    setError(null)
    try {
      const { updateClient } = await import("@/lib/api")
      await updateClient(createdClient.id, {
        description: description || undefined,
        target_audience: targetAudience || undefined,
        city: city || undefined,
        state: state || undefined,
        contact_email: contactEmail || undefined,
      })
      onClose()
      router.push(`/clients/${createdClient.id}`)
      router.refresh()
    } catch {
      setError("Failed to save details. You can finish this in Settings.")
    } finally {
      setLoading(false)
    }
  }

  function handleFinishEarly() {
    onClose()
    if (createdClient) {
      router.push(`/clients/${createdClient.id}`)
      router.refresh()
    }
  }

  const INDUSTRIES = [
    "Technology", "SaaS", "E-commerce", "Healthcare", "Finance",
    "Education", "Real Estate", "Food & Beverage", "Retail", "Other",
  ]

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {([1, 2, 3] as Step[]).map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold
                ${s === step ? "bg-primary text-primary-foreground" : ""}
                ${s < step ? "bg-primary/20 text-primary" : ""}
                ${s > step ? "bg-muted text-muted-foreground" : ""}`}
            >
              {s}
            </div>
            {s < 3 && <div className={`h-px w-8 ${s < step ? "bg-primary/40" : "bg-muted"}`} />}
          </div>
        ))}
        <span className="ml-2 text-sm text-muted-foreground">
          {step === 1 && "Brand details"}
          {step === 2 && "Competitors (optional)"}
          {step === 3 && "Profile (optional)"}
        </span>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* ── Step 1 ── */}
      {step === 1 && (
        <form onSubmit={handleStep1} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wiz-name">Brand name *</Label>
            <Input
              id="wiz-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Corp"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-website">Website *</Label>
            <Input
              id="wiz-website"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://acme.com"
              type="url"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-industry">Industry *</Label>
            <select
              id="wiz-industry"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Select industry…</option>
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Next
            </Button>
          </div>
        </form>
      )}

      {/* ── Step 2 ── */}
      {step === 2 && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Add up to 5 competitors. You can skip this and add them later in Settings.
          </p>

          {competitors.length > 0 && (
            <ul className="space-y-2">
              {competitors.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <span>
                    <span className="font-medium">{c.name}</span>
                    {c.website && (
                      <span className="text-muted-foreground ml-2">{c.website}</span>
                    )}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemoveCompetitor(c.id)}
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}

          {competitors.length < 5 && (
            <div className="flex gap-2 items-end">
              <div className="flex-1 space-y-1">
                <Label className="text-xs">Competitor name</Label>
                <Input
                  value={compName}
                  onChange={(e) => setCompName(e.target.value)}
                  placeholder="Rival Co"
                  onKeyDown={(e) => e.key === "Enter" && handleAddCompetitor()}
                />
              </div>
              <div className="flex-1 space-y-1">
                <Label className="text-xs">Website (optional)</Label>
                <Input
                  value={compWebsite}
                  onChange={(e) => setCompWebsite(e.target.value)}
                  placeholder="https://rival.com"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleAddCompetitor}
                disabled={addingComp || !compName.trim()}
              >
                {addingComp ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
              </Button>
            </div>
          )}

          <div className="flex justify-between pt-2">
            <Button variant="ghost" onClick={handleFinishEarly}>
              Skip — go to client
            </Button>
            <Button onClick={() => setStep(3)}>Next</Button>
          </div>
        </div>
      )}

      {/* ── Step 3 ── */}
      {step === 3 && (
        <form onSubmit={handleStep3} className="space-y-4">
          <p className="text-sm text-muted-foreground">
            These details improve scan quality and unlock the AI Readiness Toolkit.
          </p>
          <div className="space-y-2">
            <Label htmlFor="wiz-desc">Description</Label>
            <textarea
              id="wiz-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="3–5 sentences about the business…"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-audience">Target audience</Label>
            <Input
              id="wiz-audience"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="e.g. SME owners in Malaysia"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-city">City</Label>
              <Input
                id="wiz-city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Kuala Lumpur"
              />
            </div>
            <div className="flex-1 space-y-2">
              <Label htmlFor="wiz-state">State</Label>
              <Input
                id="wiz-state"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="Selangor"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="wiz-email">Contact email</Label>
            <Input
              id="wiz-email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              placeholder="client@example.com"
              type="email"
            />
          </div>

          <div className="flex justify-between pt-2">
            <Button variant="ghost" onClick={handleFinishEarly}>
              Skip — go to client
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Finish
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create AddClientButton**

```tsx
// frontend/src/components/clients/AddClientButton.tsx
"use client"

import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { OnboardingWizard } from "./OnboardingWizard"

export function AddClientButton() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4 mr-2" />
        Add Client
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add New Client</DialogTitle>
          </DialogHeader>
          <OnboardingWizard onClose={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  )
}
```

- [ ] **Step 3: Verify wizard end-to-end**

Start both servers:
```bash
# Terminal 1
cd backend && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

1. Visit `http://localhost:3000/clients`
2. Click "Add Client"
3. Fill in name, website, industry → click Next
4. Verify a client row now exists in the database: `GET http://localhost:8000/api/v1/clients` (with `Authorization: Bearer <key>`)
5. Add a competitor, verify it appears
6. Click "Finish" — should redirect to `/clients/<id>` (404 for now — Task 10 adds the page)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/clients/OnboardingWizard.tsx frontend/src/components/clients/AddClientButton.tsx
git commit -m "feat: add 3-step onboarding wizard and AddClientButton"
```

---

## Task 10: Frontend — Client Detail Layout + All Subpages + Settings

**Files:**
- Create: `frontend/src/app/clients/[id]/layout.tsx`
- Create: `frontend/src/app/clients/[id]/page.tsx`
- Create: `frontend/src/app/clients/[id]/scan/page.tsx`
- Create: `frontend/src/app/clients/[id]/competitors/page.tsx`
- Create: `frontend/src/app/clients/[id]/toolkit/page.tsx`
- Create: `frontend/src/app/clients/[id]/reports/page.tsx`
- Create: `frontend/src/app/clients/[id]/activity/page.tsx`
- Create: `frontend/src/app/clients/[id]/settings/page.tsx`
- Create: `frontend/src/app/clients/[id]/settings/actions.ts`

- [ ] **Step 1: Create client detail layout**

Fetches client name for the page header. In Next.js 15 params is a `Promise`.

```tsx
// frontend/src/app/clients/[id]/layout.tsx
import { notFound } from "next/navigation"
import { getClient } from "@/lib/api"

export default async function ClientLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  let client
  try {
    client = await getClient(id)
  } catch {
    notFound()
  }

  return (
    <div>
      <div className="mb-6 pb-4 border-b">
        <h1 className="text-xl font-semibold">{client.name}</h1>
        <p className="text-sm text-muted-foreground">
          <a
            href={client.website}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {client.website}
          </a>
          {" · "}
          {client.industry}
        </p>
      </div>
      {children}
    </div>
  )
}
```

- [ ] **Step 2: Create client overview page**

Shows the overall GEO score (or `—`) and each of the 5 dimension scores.

```tsx
// frontend/src/app/clients/[id]/page.tsx
import { getLatestGeoScore, getClient } from "@/lib/api"
import { ScoreBadge } from "@/components/score/ScoreBadge"

const DIMENSIONS = [
  { key: "ai_citability",       label: "AI Citability",          weight: "40%",  manual: false },
  { key: "brand_authority",     label: "Brand Authority",        weight: "20%",  manual: true  },
  { key: "content_quality",     label: "Content Quality",        weight: "20%",  manual: true  },
  { key: "technical_foundations",label: "Technical Foundations", weight: "10%",  manual: false },
  { key: "structured_data",     label: "Structured Data",        weight: "10%",  manual: false },
] as const

export default async function ClientOverviewPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [client, geoScore] = await Promise.all([
    getClient(id),
    getLatestGeoScore(id),
  ])

  return (
    <div className="space-y-6">
      {/* Overall score */}
      <div className="flex items-center gap-4 p-5 rounded-lg border bg-card">
        <div>
          <p className="text-sm text-muted-foreground font-medium">
            Overall GEO Score
          </p>
          {geoScore ? (
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-4xl font-bold">
                {geoScore.overall_score.toFixed(0)}
              </span>
              <span className="text-muted-foreground">/ 100</span>
            </div>
          ) : (
            <p className="text-2xl font-semibold text-muted-foreground mt-1">
              Awaiting first scan
            </p>
          )}
        </div>
        {geoScore && (
          <ScoreBadge
            score={geoScore.overall_score}
            className="text-sm px-3 py-1"
          />
        )}
      </div>

      {/* 5-dimension breakdown */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
          Score Breakdown
        </h2>
        <div className="space-y-2">
          {DIMENSIONS.map((dim) => {
            const raw = geoScore ? (geoScore[dim.key] as number) : null
            return (
              <div
                key={dim.key}
                className="flex items-center justify-between rounded-md border px-4 py-3 bg-card"
              >
                <div>
                  <p className="text-sm font-medium">{dim.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {dim.weight} weight
                    {dim.manual && (
                      <span className="ml-2 italic">· Assessed by SeenBy team</span>
                    )}
                  </p>
                </div>
                {raw !== null ? (
                  <ScoreBadge score={raw} />
                ) : (
                  <ScoreBadge score={null} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Manual score update notice */}
      {!geoScore && (
        <p className="text-sm text-muted-foreground text-center py-4">
          Scores will appear after the first scan is completed.
        </p>
      )}

      {geoScore && (
        <p className="text-xs text-muted-foreground">
          Score computed{" "}
          {new Date(geoScore.computed_at).toLocaleDateString("en-MY", {
            day: "numeric",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create 5 placeholder pages**

Each placeholder has the same shape:

```tsx
// frontend/src/app/clients/[id]/scan/page.tsx
export default function ScanPage() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
      <p className="font-medium">Scan &amp; Visibility</p>
      <p className="text-sm mt-1">Coming in Plan 3.</p>
    </div>
  )
}
```

```tsx
// frontend/src/app/clients/[id]/competitors/page.tsx
export default function CompetitorsPage() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
      <p className="font-medium">Competitor Intelligence</p>
      <p className="text-sm mt-1">Coming in Plan 4.</p>
    </div>
  )
}
```

```tsx
// frontend/src/app/clients/[id]/toolkit/page.tsx
export default function ToolkitPage() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
      <p className="font-medium">AI Readiness Toolkit</p>
      <p className="text-sm mt-1">Coming in Plan 3.</p>
    </div>
  )
}
```

```tsx
// frontend/src/app/clients/[id]/reports/page.tsx
export default function ReportsPage() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
      <p className="font-medium">Reports</p>
      <p className="text-sm mt-1">Coming in Plan 7.</p>
    </div>
  )
}
```

```tsx
// frontend/src/app/clients/[id]/activity/page.tsx
export default function ActivityPage() {
  return (
    <div className="rounded-lg border border-dashed p-10 text-center text-muted-foreground">
      <p className="font-medium">Activity Log</p>
      <p className="text-sm mt-1">Coming in Plan 5.</p>
    </div>
  )
}
```

- [ ] **Step 4: Create settings actions**

```typescript
// frontend/src/app/clients/[id]/settings/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import { updateClient } from "@/lib/api"

export async function updateClientAction(
  id: string,
  data: {
    name?: string
    website?: string
    industry?: string
    description?: string
    target_audience?: string
    city?: string
    state?: string
    contact_email?: string
    brand_authority_score?: number
    content_quality_score?: number
    score_drop_threshold?: number
  },
) {
  const client = await updateClient(id, data)
  revalidatePath(`/clients/${id}`)
  revalidatePath("/clients")
  return client
}
```

- [ ] **Step 5: Create settings page**

```tsx
// frontend/src/app/clients/[id]/settings/page.tsx
import { getClient, getCompetitors } from "@/lib/api"
import { SettingsForm } from "./SettingsForm"

export default async function SettingsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const [client, competitors] = await Promise.all([
    getClient(id),
    getCompetitors(id),
  ])

  return (
    <div className="max-w-2xl space-y-8">
      <SettingsForm client={client} competitors={competitors} />
    </div>
  )
}
```

- [ ] **Step 6: Create SettingsForm client component**

The settings form is a client component co-located in the settings folder:

```tsx
// frontend/src/app/clients/[id]/settings/SettingsForm.tsx
"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { updateClientAction } from "./actions"
import {
  addCompetitorAction,
  deleteCompetitorAction,
} from "@/app/clients/actions"
import { Trash2, Plus, Loader2, CheckCircle } from "lucide-react"
import type { Client, Competitor } from "@/types"

interface Props {
  client: Client
  competitors: Competitor[]
}

export function SettingsForm({ client, competitors: initialCompetitors }: Props) {
  const [isPending, startTransition] = useTransition()
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [competitors, setCompetitors] = useState<Competitor[]>(initialCompetitors)
  const [compName, setCompName] = useState("")
  const [compWebsite, setCompWebsite] = useState("")
  const [addingComp, setAddingComp] = useState(false)

  async function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    setError(null)
    setSaved(false)
    startTransition(async () => {
      try {
        await updateClientAction(client.id, {
          name: fd.get("name") as string,
          website: fd.get("website") as string,
          industry: fd.get("industry") as string,
          description: (fd.get("description") as string) || undefined,
          target_audience: (fd.get("target_audience") as string) || undefined,
          city: (fd.get("city") as string) || undefined,
          state: (fd.get("state") as string) || undefined,
          contact_email: (fd.get("contact_email") as string) || undefined,
          brand_authority_score: fd.get("brand_authority_score")
            ? Number(fd.get("brand_authority_score"))
            : undefined,
          content_quality_score: fd.get("content_quality_score")
            ? Number(fd.get("content_quality_score"))
            : undefined,
          score_drop_threshold: fd.get("score_drop_threshold")
            ? Number(fd.get("score_drop_threshold"))
            : undefined,
        })
        setSaved(true)
      } catch {
        setError("Failed to save. Please try again.")
      }
    })
  }

  async function handleAddComp() {
    if (!compName.trim()) return
    setAddingComp(true)
    try {
      const comp = await addCompetitorAction(client.id, {
        name: compName.trim(),
        website: compWebsite.trim() || undefined,
      })
      setCompetitors((prev) => [...prev, comp])
      setCompName("")
      setCompWebsite("")
    } catch {
      setError("Failed to add competitor.")
    } finally {
      setAddingComp(false)
    }
  }

  async function handleRemoveComp(id: string) {
    try {
      await deleteCompetitorAction(client.id, id)
      setCompetitors((prev) => prev.filter((c) => c.id !== id))
    } catch {
      setError("Failed to remove competitor.")
    }
  }

  const INDUSTRIES = [
    "Technology", "SaaS", "E-commerce", "Healthcare", "Finance",
    "Education", "Real Estate", "Food & Beverage", "Retail", "Other",
  ]

  return (
    <form onSubmit={handleSave} className="space-y-8">
      {/* Brand details */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Brand Details</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 space-y-1">
            <Label htmlFor="s-name">Brand name</Label>
            <Input id="s-name" name="name" defaultValue={client.name} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-website">Website</Label>
            <Input id="s-website" name="website" defaultValue={client.website} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-industry">Industry</Label>
            <select
              id="s-industry"
              name="industry"
              defaultValue={client.industry}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {INDUSTRIES.map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <Separator />

      {/* Profile */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">Profile</h2>
        <div className="space-y-1">
          <Label htmlFor="s-desc">Description</Label>
          <textarea
            id="s-desc"
            name="description"
            defaultValue={client.description ?? ""}
            rows={3}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-audience">Target audience</Label>
          <Input
            id="s-audience"
            name="target_audience"
            defaultValue={client.target_audience ?? ""}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-city">City</Label>
            <Input id="s-city" name="city" defaultValue={client.city ?? ""} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-state">State</Label>
            <Input id="s-state" name="state" defaultValue={client.state ?? ""} />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-email">Contact email</Label>
          <Input
            id="s-email"
            name="contact_email"
            type="email"
            defaultValue={client.contact_email ?? ""}
          />
        </div>
      </section>

      <Separator />

      {/* Manual scores — "Assessed by SeenBy team" */}
      <section className="space-y-4">
        <div>
          <h2 className="text-base font-semibold">Manual Score Inputs</h2>
          <p className="text-xs text-muted-foreground mt-0.5 italic">
            Assessed by SeenBy team
          </p>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label htmlFor="s-authority">Brand Authority (0–100)</Label>
            <Input
              id="s-authority"
              name="brand_authority_score"
              type="number"
              min="0"
              max="100"
              defaultValue={client.brand_authority_score}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-content">Content Quality (0–100)</Label>
            <Input
              id="s-content"
              name="content_quality_score"
              type="number"
              min="0"
              max="100"
              defaultValue={client.content_quality_score}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="s-threshold">Score Drop Threshold</Label>
            <Input
              id="s-threshold"
              name="score_drop_threshold"
              type="number"
              min="0"
              max="100"
              defaultValue={client.score_drop_threshold}
            />
          </div>
        </div>
      </section>

      <Separator />

      {/* Competitors */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold">
          Competitors ({competitors.length}/5)
        </h2>
        {competitors.length > 0 && (
          <ul className="space-y-2">
            {competitors.map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  <span className="font-medium">{c.name}</span>
                  {c.website && (
                    <span className="text-muted-foreground ml-2">{c.website}</span>
                  )}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRemoveComp(c.id)}
                  className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {competitors.length < 5 && (
          <div className="flex gap-2 items-end">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Name</Label>
              <Input
                value={compName}
                onChange={(e) => setCompName(e.target.value)}
                placeholder="Rival Co"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Website (optional)</Label>
              <Input
                value={compWebsite}
                onChange={(e) => setCompWebsite(e.target.value)}
                placeholder="https://rival.com"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={handleAddComp}
              disabled={addingComp || !compName.trim()}
            >
              {addingComp ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}
      </section>

      {/* Save footer */}
      <div className="flex items-center gap-3 pt-2">
        <Button type="submit" disabled={isPending}>
          {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          Save changes
        </Button>
        {saved && (
          <span className="flex items-center gap-1 text-sm text-green-600">
            <CheckCircle className="h-4 w-4" />
            Saved
          </span>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </form>
  )
}
```

- [ ] **Step 7: Verify all routes work**

```bash
cd frontend && npm run dev
```

Checklist:
- [ ] `/clients` — shows client list or empty state with Add Client button
- [ ] Click "Add Client" — wizard opens
- [ ] Complete Step 1 — client created, wizard moves to Step 2
- [ ] Click "Skip — go to client" — redirects to `/clients/<id>`
- [ ] `/clients/<id>` — shows client name in header, `—` score or score if one exists
- [ ] `/clients/<id>/scan` — shows placeholder
- [ ] `/clients/<id>/competitors` — shows placeholder
- [ ] `/clients/<id>/toolkit` — shows placeholder
- [ ] `/clients/<id>/reports` — shows placeholder
- [ ] `/clients/<id>/activity` — shows placeholder
- [ ] `/clients/<id>/settings` — shows form with client data
- [ ] Edit a field in Settings, click Save — data updates
- [ ] Sidebar shows all 7 client nav links when inside a client page
- [ ] Logout button signs out and redirects to `/auth/login`

- [ ] **Step 8: TypeScript check**

```bash
cd frontend && npm run typecheck
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add "frontend/src/app/clients/[id]/"
git commit -m "feat: add client detail layout, overview, placeholder pages, and settings"
```

---

## Verification (per spec)

From `docs/mvp-scope.md` — Plan 2 acceptance criteria:

- [ ] Login flow works — `/auth/login` accepts configured credentials, rejects wrong ones
- [ ] All 8 routes accessible (no 404s after auth)
- [ ] Onboarding wizard creates correct DB rows — Step 1 → `clients` row with `archived_at = null`; Step 2 → `competitors` rows; Step 3 → updates client fields
- [ ] Client card shows `—` before first scan, score badge when score exists
- [ ] Settings page can update manual scores (`brand_authority_score`, `content_quality_score`)
- [ ] Sidebar shows context-correct nav (client sub-nav only when inside `/clients/[id]/*`)

---

## Memory Update

After completing this plan, update the project memory file to note Plan 2 is done and record the plan file path.
