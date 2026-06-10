# SeenBy Plan 3: AI Readiness Toolkit + Verification Crawler

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the AI Readiness Toolkit — a backend service that generates three AI-readiness files (llms.txt, schema.json, robots.txt) via Claude API, stores them per-client, and verifies they are live at the client's domain; plus a frontend UI on the Toolkit page replacing the placeholder.

**Architecture:** The backend gains a `toolkit_files` table (one row per client), a generation service that calls the Anthropic SDK for llms.txt and schema.json and constructs robots.txt deterministically, a verification crawler using httpx to check live URLs, and three REST endpoints under `/api/v1/clients/{id}/toolkit/`. The frontend Toolkit page becomes a real UI with a server component that pre-fetches any existing files and a client component that handles generate/verify interactions, copy/download per-file, and implementation instructions. When verification passes, `technical_foundations_verified` (llms.txt live) and `structured_data_verified` (schema.json live) are updated on the client — automatically boosting the GEO score by up to 20 points.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Alembic · Anthropic Python SDK · httpx · Next.js 15 · React 19 · TypeScript · shadcn/ui

---

## File Map

```
backend/
├── app/
│   ├── core/
│   │   └── config.py                        MODIFY: add ANTHROPIC_API_KEY
│   ├── models/
│   │   └── toolkit_files.py                 CREATE: ToolkitFiles ORM model
│   ├── schemas/
│   │   └── toolkit.py                       CREATE: ToolkitFilesResponse, VerificationResult
│   ├── services/
│   │   ├── toolkit_service.py               CREATE: generate_llms_txt, generate_schema_json, generate_robots_txt
│   │   └── verification_crawler.py          CREATE: verify_llms_txt, verify_schema_json, verify_robots_txt, verify_all
│   └── api/v1/
│       ├── toolkit.py                       CREATE: generate, get_files, verify endpoints
│       └── router.py                        MODIFY: register toolkit router
├── alembic/
│   └── env.py                               MODIFY: import toolkit_files model
└── tests/
    ├── test_toolkit_service.py              CREATE
    ├── test_verification_crawler.py         CREATE
    └── test_api_toolkit.py                  CREATE

frontend/
└── src/
    ├── types/
    │   └── index.ts                         MODIFY: add ToolkitFiles, VerificationResult
    ├── lib/
    │   └── api.ts                           MODIFY: add getToolkitFiles, generateToolkitFiles, verifyToolkitFiles
    └── app/clients/[id]/toolkit/
        ├── page.tsx                         MODIFY: replace placeholder with server component
        ├── ToolkitClient.tsx                CREATE: client component (generate/verify UI, tabs, copy/download)
        └── actions.ts                       CREATE: generateToolkitAction, verifyToolkitAction
```

---

## Task 1: Backend — ToolkitFiles Model + Alembic Migration

**Files:**
- Create: `backend/app/models/toolkit_files.py`
- Modify: `backend/alembic/env.py`

- [ ] **Step 1: Create ToolkitFiles model**

```python
# backend/app/models/toolkit_files.py
import uuid
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ToolkitFiles(Base):
    __tablename__ = "toolkit_files"
    __table_args__ = (UniqueConstraint("client_id", name="uq_toolkit_files_client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    llms_txt: Mapped[str] = mapped_column(Text, nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    robots_txt: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    llms_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    schema_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 2: Add import to alembic/env.py**

Open `backend/alembic/env.py`. The current import line is:

```python
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log  # noqa: F401
```

Replace with:

```python
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log, toolkit_files  # noqa: F401
```

- [ ] **Step 3: Generate and apply migration**

With the backend virtualenv active and `DATABASE_URL` pointing to your running Postgres:

```bash
cd backend
alembic revision --autogenerate -m "add toolkit_files table"
alembic upgrade head
```

Expected: Alembic creates a new file in `alembic/versions/` and applies it. You will see:
```
Running upgrade  -> <rev_id>, add toolkit_files table
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/toolkit_files.py backend/alembic/env.py backend/alembic/versions/
git commit -m "feat: add toolkit_files model and migration"
```

---

## Task 2: Backend — Config + Dependencies + Toolkit Generation Service

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/toolkit_service.py`
- Create: `backend/tests/test_toolkit_service.py`

- [ ] **Step 1: Write failing tests for toolkit service**

```python
# backend/tests/test_toolkit_service.py
from unittest.mock import MagicMock, patch
from app.services.toolkit_service import generate_robots_txt, generate_llms_txt, generate_schema_json


def _fake_client():
    m = MagicMock()
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = "An AI company"
    m.target_audience = "developers"
    m.city = "Kuala Lumpur"
    m.state = "Selangor"
    return m


def test_generate_robots_txt_contains_required_bots():
    client = _fake_client()
    result = generate_robots_txt(client)
    assert "GPTBot" in result
    assert "PerplexityBot" in result
    assert "ClaudeBot" in result
    assert "Google-Extended" in result
    assert "Allow: /" in result


def test_generate_robots_txt_contains_client_domain():
    client = _fake_client()
    result = generate_robots_txt(client)
    assert "acme.com" in result


def test_generate_llms_txt_calls_claude_and_returns_content():
    client = _fake_client()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Acme Corp\n> tagline")]

    with patch("app.services.toolkit_service._anthropic_client") as mock_client_fn:
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_anthropic
        result = generate_llms_txt(client)

    assert result == "# Acme Corp\n> tagline"
    mock_anthropic.messages.create.assert_called_once()


def test_generate_schema_json_calls_claude_and_returns_content():
    client = _fake_client()
    schema = '{"@context": "https://schema.org", "@graph": []}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=schema)]

    with patch("app.services.toolkit_service._anthropic_client") as mock_client_fn:
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_anthropic
        result = generate_schema_json(client)

    assert result == schema
    mock_anthropic.messages.create.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure (module not found)**

```bash
cd backend
pytest tests/test_toolkit_service.py -v
```

Expected: `ModuleNotFoundError` — `toolkit_service` doesn't exist yet.

- [ ] **Step 3: Add anthropic and httpx to main dependencies**

Open `backend/pyproject.toml`. In `[tool.poetry.dependencies]`, add:

```toml
anthropic = "^0.50"
httpx = "^0.28"
```

Also remove `httpx` from `[tool.poetry.group.dev.dependencies]` (it's now a main dep).

After editing:

```bash
cd backend
poetry add anthropic httpx
```

Expected: packages installed into the virtualenv.

- [ ] **Step 4: Add ANTHROPIC_API_KEY to config.py**

Open `backend/app/core/config.py`. Replace the full file with:

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
    ANTHROPIC_API_KEY: str

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
```

- [ ] **Step 5: Add ANTHROPIC_API_KEY to backend/.env**

Open `backend/.env` and add:

```
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

- [ ] **Step 6: Create toolkit_service.py**

```python
# backend/app/services/toolkit_service.py
import anthropic
from app.core.config import settings
from app.models.client import Client

_MODEL = "claude-haiku-4-5-20251001"


def _anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def generate_llms_txt(client: Client) -> str:
    response = _anthropic_client().messages.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""Generate an llms.txt file for this business.
llms.txt is a standard file (similar to robots.txt) that helps AI language models understand a website.
Follow the Answer.AI spec: start with # Brand Name on the first line, then > short one-sentence tagline, then markdown sections with relevant information.

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or 'Not provided'}
Target audience: {client.target_audience or 'Not provided'}
City: {client.city or 'Not provided'}
State: {client.state or 'Not provided'}

Output ONLY the raw llms.txt content. No explanations. No code block wrappers.""",
            }
        ],
    )
    return response.content[0].text.strip()


def generate_schema_json(client: Client) -> str:
    response = _anthropic_client().messages.create(
        model=_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""Generate a JSON-LD structured data file for this business.
Include these schema types in a @graph array:
1. LocalBusiness (or an appropriate subtype like ProfessionalService, Restaurant, etc.)
2. Organization
3. FAQPage with 3-5 realistic FAQ items about this specific business

Business details:
Name: {client.name}
Website: {client.website}
Industry: {client.industry}
Description: {client.description or 'Not provided'}
City: {client.city or 'Not provided'}
State: {client.state or 'Not provided'}

Output ONLY valid JSON. No explanations. No ```json code block wrapper. Start directly with the opening brace.""",
            }
        ],
    )
    return response.content[0].text.strip()


def generate_robots_txt(client: Client) -> str:
    return f"""# AI Search Bot Access — generated by SeenBy
# Add these lines to your existing robots.txt file at {client.website}/robots.txt

User-agent: GPTBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /"""


def generate_toolkit_files(client: Client) -> dict[str, str]:
    return {
        "llms_txt": generate_llms_txt(client),
        "schema_json": generate_schema_json(client),
        "robots_txt": generate_robots_txt(client),
    }
```

- [ ] **Step 7: Run tests — expect pass**

```bash
cd backend
pytest tests/test_toolkit_service.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/poetry.lock backend/app/core/config.py backend/app/services/toolkit_service.py backend/tests/test_toolkit_service.py
git commit -m "feat: add ANTHROPIC_API_KEY config and toolkit generation service"
```

---

## Task 3: Backend — Verification Crawler Service

**Files:**
- Create: `backend/app/services/verification_crawler.py`
- Create: `backend/tests/test_verification_crawler.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_verification_crawler.py
from unittest.mock import MagicMock, patch
from app.services.verification_crawler import (
    verify_llms_txt,
    verify_schema_json,
    verify_robots_txt,
    _domain_base,
)


def test_domain_base_strips_path():
    assert _domain_base("https://acme.com/about") == "https://acme.com"


def test_domain_base_keeps_subdomain():
    assert _domain_base("https://www.acme.com") == "https://www.acme.com"


def test_domain_base_adds_https_when_no_scheme():
    assert _domain_base("acme.com") == "https://acme.com"


def test_verify_llms_txt_returns_true_on_200_with_content():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "# Acme Corp\n> tagline"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_llms_txt("https://acme.com") is True


def test_verify_llms_txt_returns_false_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = ""

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_llms_txt("https://acme.com") is False


def test_verify_llms_txt_returns_false_on_exception():
    with patch("app.services.verification_crawler.httpx.get", side_effect=Exception("timeout")):
        assert verify_llms_txt("https://acme.com") is False


def test_verify_schema_json_returns_true_on_valid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"@context": "https://schema.org"}

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is True


def test_verify_schema_json_returns_false_on_invalid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("not json")

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is False


def test_verify_schema_json_returns_false_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is False


def test_verify_robots_txt_returns_true_when_gptbot_present():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "User-agent: *\nDisallow: /private\n\nUser-agent: GPTBot\nAllow: /"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_robots_txt("https://acme.com") is True


def test_verify_robots_txt_returns_false_when_gptbot_absent():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "User-agent: *\nDisallow:"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_robots_txt("https://acme.com") is False


def test_verify_robots_txt_returns_false_on_exception():
    with patch("app.services.verification_crawler.httpx.get", side_effect=Exception("refused")):
        assert verify_robots_txt("https://acme.com") is False
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
pytest tests/test_verification_crawler.py -v
```

Expected: `ModuleNotFoundError` — `verification_crawler` doesn't exist yet.

- [ ] **Step 3: Create verification_crawler.py**

```python
# backend/app/services/verification_crawler.py
from urllib.parse import urlparse

import httpx

_TIMEOUT = 10


def _domain_base(website: str) -> str:
    if "://" not in website:
        website = f"https://{website}"
    parsed = urlparse(website)
    return f"{parsed.scheme}://{parsed.netloc}"


def verify_llms_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/llms.txt"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        return r.status_code == 200 and len(r.text.strip()) > 0
    except Exception:
        return False


def verify_schema_json(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/schema.json"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return False
        r.json()
        return True
    except Exception:
        return False


def verify_robots_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/robots.txt"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return False
        return "gptbot" in r.text.lower()
    except Exception:
        return False


def verify_all(website: str) -> dict[str, bool]:
    return {
        "llms_verified": verify_llms_txt(website),
        "schema_verified": verify_schema_json(website),
        "robots_verified": verify_robots_txt(website),
    }
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend
pytest tests/test_verification_crawler.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/verification_crawler.py backend/tests/test_verification_crawler.py
git commit -m "feat: add verification crawler service"
```

---

## Task 4: Backend — Toolkit API Schemas + Endpoints + Router

**Files:**
- Create: `backend/app/schemas/toolkit.py`
- Create: `backend/app/api/v1/toolkit.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_api_toolkit.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_api_toolkit.py
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch
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
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = "An AI company"
    m.target_audience = "developers"
    m.city = "Kuala Lumpur"
    m.state = "Selangor"
    m.technical_foundations_verified = False
    m.structured_data_verified = False
    return m


def _fake_toolkit(client_id):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.client_id = client_id
    m.llms_txt = "# Acme Corp\n> tagline"
    m.schema_json = '{"@context": "https://schema.org", "@graph": []}'
    m.robots_txt = "User-agent: GPTBot\nAllow: /"
    m.generated_at = datetime(2026, 1, 1)
    m.llms_verified = False
    m.schema_verified = False
    m.robots_verified = False
    m.verified_at = None
    return m


def test_get_files_returns_null_when_not_generated():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{fake_client.id}/toolkit/files")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() is None


def test_generate_creates_new_toolkit_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)

    def fake_refresh(obj):
        obj.id = fake_tf.id
        obj.client_id = fake_tf.client_id
        obj.llms_txt = fake_tf.llms_txt
        obj.schema_json = fake_tf.schema_json
        obj.robots_txt = fake_tf.robots_txt
        obj.generated_at = fake_tf.generated_at
        obj.llms_verified = fake_tf.llms_verified
        obj.schema_verified = fake_tf.schema_verified
        obj.robots_verified = fake_tf.robots_verified
        obj.verified_at = fake_tf.verified_at

    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.generate_toolkit_files") as mock_gen:
        mock_gen.return_value = {
            "llms_txt": fake_tf.llms_txt,
            "schema_json": fake_tf.schema_json,
            "robots_txt": fake_tf.robots_txt,
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/generate")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["llms_txt"] == fake_tf.llms_txt
    assert data["schema_json"] == fake_tf.schema_json
    assert data["robots_txt"] == fake_tf.robots_txt


def test_generate_updates_existing_toolkit_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    # Simulate existing row
    existing = MagicMock()
    existing.id = fake_tf.id
    existing.client_id = fake_tf.client_id
    existing.llms_txt = "old content"
    existing.schema_json = "{}"
    existing.robots_txt = "old"
    existing.generated_at = datetime(2025, 1, 1)
    existing.llms_verified = True
    existing.schema_verified = True
    existing.robots_verified = True
    existing.verified_at = datetime(2025, 1, 2)

    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = existing
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.generate_toolkit_files") as mock_gen:
        mock_gen.return_value = {
            "llms_txt": "# New",
            "schema_json": '{"@context": "new"}',
            "robots_txt": "User-agent: GPTBot\nAllow: /",
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/generate")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    # Verification flags should be reset on regeneration
    assert existing.llms_verified is False
    assert existing.schema_verified is False
    assert existing.robots_verified is False
    assert existing.verified_at is None


def test_verify_returns_verification_results():
    app, get_db = _make_app()
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db

    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": True,
            "schema_verified": True,
            "robots_verified": True,
        }
        http = TestClient(app)
        resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["llms_verified"] is True
    assert data["schema_verified"] is True
    assert data["robots_verified"] is True
    assert data["technical_foundations_updated"] is True
    assert data["structured_data_updated"] is True


def test_verify_returns_404_when_no_files():
    app, get_db = _make_app()
    fake_client = _fake_client()
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{fake_client.id}/toolkit/verify")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_generate_requires_auth():
    from app.main import app
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{uuid.uuid4()}/toolkit/generate")
    assert resp.status_code == 401


def test_get_client_not_found_returns_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/toolkit/files")
    app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
pytest tests/test_api_toolkit.py -v
```

Expected: FAIL — routes don't exist yet.

- [ ] **Step 3: Create toolkit schemas**

```python
# backend/app/schemas/toolkit.py
import uuid
from datetime import datetime
from pydantic import BaseModel


class ToolkitFilesResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    llms_txt: str
    schema_json: str
    robots_txt: str
    generated_at: datetime
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    verified_at: datetime | None = None

    model_config = {"from_attributes": True}


class VerificationResult(BaseModel):
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    technical_foundations_updated: bool
    structured_data_updated: bool
```

- [ ] **Step 4: Create toolkit API**

```python
# backend/app/api/v1/toolkit.py
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
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
        existing.generated_at = datetime.utcnow()
        existing.llms_verified = False
        existing.schema_verified = False
        existing.robots_verified = False
        existing.verified_at = None
        db.commit()
        db.refresh(existing)
        return existing

    tf = ToolkitFiles(client_id=client_id, **files_content)
    db.add(tf)
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
        tf.verified_at = datetime.utcnow()

    client.technical_foundations_verified = results["llms_verified"]
    client.structured_data_verified = results["schema_verified"]

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

- [ ] **Step 5: Register toolkit router**

Open `backend/app/api/v1/router.py`. Replace with:

```python
# backend/app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors, toolkit

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
router.include_router(toolkit.router)
```

- [ ] **Step 6: Run all backend tests — expect all pass**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests PASS (toolkit service, crawler, and API tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/toolkit.py backend/app/api/v1/toolkit.py backend/app/api/v1/router.py backend/tests/test_api_toolkit.py
git commit -m "feat: add toolkit API endpoints and register router"
```

---

## Task 5: Frontend — Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add ToolkitFiles and VerificationResult to types**

Open `frontend/src/types/index.ts`. Append at the end of the file:

```typescript
export interface ToolkitFiles {
  id: string
  client_id: string
  llms_txt: string
  schema_json: string
  robots_txt: string
  generated_at: string
  llms_verified: boolean
  schema_verified: boolean
  robots_verified: boolean
  verified_at: string | null
}

export interface VerificationResult {
  llms_verified: boolean
  schema_verified: boolean
  robots_verified: boolean
  technical_foundations_updated: boolean
  structured_data_updated: boolean
}
```

- [ ] **Step 2: Add toolkit API functions to api.ts**

Open `frontend/src/lib/api.ts`. Append after the `deleteCompetitor` function:

```typescript
// ── Toolkit ───────────────────────────────────────────────────────────────────

export function getToolkitFiles(clientId: string): Promise<ToolkitFiles | null> {
  return apiFetch<ToolkitFiles | null>(`/api/v1/clients/${clientId}/toolkit/files`)
}

export function generateToolkitFiles(clientId: string): Promise<ToolkitFiles> {
  return apiFetch<ToolkitFiles>(`/api/v1/clients/${clientId}/toolkit/generate`, {
    method: "POST",
  })
}

export function verifyToolkitFiles(clientId: string): Promise<VerificationResult> {
  return apiFetch<VerificationResult>(`/api/v1/clients/${clientId}/toolkit/verify`, {
    method: "POST",
  })
}
```

Also update the import at the top of `api.ts` to include the new types. The current import is:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore } from "@/types"
```

Replace with:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult } from "@/types"
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add ToolkitFiles types and toolkit API functions"
```

---

## Task 6: Frontend — Toolkit Page UI

**Files:**
- Create: `frontend/src/app/clients/[id]/toolkit/actions.ts`
- Create: `frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx`
- Modify: `frontend/src/app/clients/[id]/toolkit/page.tsx`

- [ ] **Step 1: Create server actions**

```typescript
// frontend/src/app/clients/[id]/toolkit/actions.ts
"use server"

import { revalidatePath } from "next/cache"
import {
  generateToolkitFiles as apiGenerate,
  verifyToolkitFiles as apiVerify,
} from "@/lib/api"
import type { ToolkitFiles, VerificationResult } from "@/types"

export async function generateToolkitAction(clientId: string): Promise<ToolkitFiles> {
  const files = await apiGenerate(clientId)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return files
}

export async function verifyToolkitAction(clientId: string): Promise<VerificationResult> {
  const result = await apiVerify(clientId)
  revalidatePath(`/clients/${clientId}`)
  revalidatePath(`/clients/${clientId}/toolkit`)
  return result
}
```

- [ ] **Step 2: Create ToolkitClient component**

```tsx
// frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx
"use client"

import { useState, useTransition } from "react"
import { Loader2, Copy, Download, CheckCircle, XCircle, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { generateToolkitAction, verifyToolkitAction } from "./actions"
import type { ToolkitFiles, VerificationResult } from "@/types"

interface Props {
  clientId: string
  initialFiles: ToolkitFiles | null
}

const FILE_META = {
  llms_txt: {
    label: "llms.txt",
    filename: "llms.txt",
    instruction:
      'Upload this file to your website root so it\'s accessible at yourdomain.com/llms.txt. Most hosting providers let you upload via FTP or file manager. No plugin or configuration needed.',
    expectedUrl: "/llms.txt",
  },
  schema_json: {
    label: "schema.json",
    filename: "schema.json",
    instruction:
      'Upload this file to your website root (yourdomain.com/schema.json), or embed its contents between <script type="application/ld+json"> tags in your site\'s <head>. WordPress users: use the "Schema & Structured Data for WP" plugin and paste the JSON there.',
    expectedUrl: "/schema.json",
  },
  robots_txt: {
    label: "robots.txt",
    filename: "robots.txt",
    instruction:
      "Copy these lines and paste them at the bottom of your existing robots.txt file (yourdomain.com/robots.txt). If you don't have a robots.txt yet, create one and use this as its full content.",
    expectedUrl: "/robots.txt",
  },
} as const

type FileKey = keyof typeof FILE_META
const FILE_KEYS: FileKey[] = ["llms_txt", "schema_json", "robots_txt"]

export function ToolkitClient({ clientId, initialFiles }: Props) {
  const [files, setFiles] = useState<ToolkitFiles | null>(initialFiles)
  const [activeTab, setActiveTab] = useState<FileKey>("llms_txt")
  const [verification, setVerification] = useState<VerificationResult | null>(null)
  const [copied, setCopied] = useState<FileKey | null>(null)
  const [isPending, startGenTransition] = useTransition()
  const [isVerifying, startVerifyTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleGenerate() {
    startGenTransition(async () => {
      setError(null)
      try {
        const result = await generateToolkitAction(clientId)
        setFiles(result)
        setVerification(null)
      } catch {
        setError("Failed to generate files. Please try again.")
      }
    })
  }

  function handleVerify() {
    startVerifyTransition(async () => {
      setError(null)
      try {
        const result = await verifyToolkitAction(clientId)
        setVerification(result)
        if (files) {
          setFiles({
            ...files,
            llms_verified: result.llms_verified,
            schema_verified: result.schema_verified,
            robots_verified: result.robots_verified,
          })
        }
      } catch {
        setError("Verification failed. Please try again.")
      }
    })
  }

  function handleCopy(key: FileKey) {
    navigator.clipboard.writeText(files![key])
    setCopied(key)
    setTimeout(() => setCopied(null), 2000)
  }

  function handleDownload(key: FileKey) {
    const blob = new Blob([files![key]], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = FILE_META[key].filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function isVerified(key: FileKey): boolean {
    if (!files) return false
    if (key === "llms_txt") return files.llms_verified
    if (key === "schema_json") return files.schema_verified
    return files.robots_verified
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">AI Readiness Toolkit</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Generate the three files that make your client visible to AI search engines.
            Each verified file unlocks score points.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {files && (
            <Button variant="outline" onClick={handleVerify} disabled={isVerifying}>
              {isVerifying ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Verify live
            </Button>
          )}
          <Button onClick={handleGenerate} disabled={isPending}>
            {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {files ? "Regenerate" : "Generate files"}
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Empty state */}
      {!files && !isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No files generated yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate files&rdquo; to create your AI readiness toolkit.
          </p>
        </div>
      )}

      {/* Generating state */}
      {isPending && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3" />
          <p className="text-sm font-medium">Generating files with Claude AI…</p>
          <p className="text-xs mt-1">This usually takes 10–20 seconds.</p>
        </div>
      )}

      {/* Files UI */}
      {files && !isPending && (
        <>
          {/* Tab bar */}
          <div className="flex gap-0 border-b">
            {FILE_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  activeTab === key
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {FILE_META[key].label}
                  {isVerified(key) ? (
                    <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-muted-foreground/40" />
                  )}
                </span>
              </button>
            ))}
          </div>

          {/* Tab content */}
          {FILE_KEYS.map((key) =>
            activeTab !== key ? null : (
              <div key={key} className="space-y-4">
                {/* File content area */}
                <div className="relative rounded-md border bg-muted/20">
                  <div className="absolute top-2 right-2 flex gap-1 z-10">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs bg-background"
                      onClick={() => handleCopy(key)}
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      {copied === key ? "Copied!" : "Copy"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs bg-background"
                      onClick={() => handleDownload(key)}
                    >
                      <Download className="h-3 w-3 mr-1" />
                      Download
                    </Button>
                  </div>
                  <textarea
                    readOnly
                    value={files[key]}
                    rows={14}
                    className="w-full rounded-md bg-transparent px-3 py-3 pt-10 text-xs font-mono resize-none focus:outline-none"
                  />
                </div>

                {/* Instructions */}
                <div className="rounded-md border bg-muted/10 px-4 py-3 space-y-2">
                  <p className="text-sm font-medium">How to implement</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {FILE_META[key].instruction}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Expected URL:{" "}
                    <code className="font-mono bg-muted px-1 py-0.5 rounded text-xs">
                      {FILE_META[key].expectedUrl}
                    </code>
                  </p>
                </div>

                {/* Verification badge */}
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Live status:</span>
                  {isVerified(key) ? (
                    <Badge className="bg-green-100 text-green-800 border-green-200 gap-1">
                      <CheckCircle className="h-3 w-3" />
                      Verified live
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground gap-1">
                      <XCircle className="h-3 w-3" />
                      Not yet verified
                    </Badge>
                  )}
                </div>
              </div>
            )
          )}

          {/* Score impact panel — shown after any verification attempt */}
          {verification && (
            <div className="rounded-md border px-4 py-3 space-y-2">
              <p className="text-sm font-semibold">Score impact</p>
              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Technical Foundations (10 pts)</span>
                  {verification.technical_foundations_updated ? (
                    <span className="text-green-600 font-medium">✓ Unlocked — llms.txt is live</span>
                  ) : (
                    <span className="text-muted-foreground">Needs llms.txt live at your domain</span>
                  )}
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Structured Data (10 pts)</span>
                  {verification.structured_data_updated ? (
                    <span className="text-green-600 font-medium">✓ Unlocked — schema.json is live</span>
                  ) : (
                    <span className="text-muted-foreground">Needs schema.json live at your domain</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Replace placeholder page.tsx with server component**

```tsx
// frontend/src/app/clients/[id]/toolkit/page.tsx
import { getToolkitFiles } from "@/lib/api"
import { ToolkitClient } from "./ToolkitClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ToolkitPage({ params }: Props) {
  const { id } = await params
  let files = null
  try {
    files = await getToolkitFiles(id)
  } catch {
    // Backend down or client not found — show empty state
  }
  return <ToolkitClient clientId={id} initialFiles={files} />
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Start dev server and manually test the toolkit page**

```bash
cd frontend
npm run dev
```

1. Navigate to any client's Toolkit page (`/clients/{id}/toolkit`)
2. Click **Generate files** — should show loading spinner, then display 3 tabs
3. Click each tab — verify file content is shown, copy button works, download button downloads the file
4. Read implementation instructions for each tab — verify they make sense
5. Click **Verify live** — for a test domain that hasn't uploaded files, all three should show "Not yet verified"
6. Confirm score impact panel appears after verification

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/app/clients/[id]/toolkit/actions.ts" "frontend/src/app/clients/[id]/toolkit/ToolkitClient.tsx" "frontend/src/app/clients/[id]/toolkit/page.tsx"
git commit -m "feat: build AI Readiness Toolkit page with generate, copy, download, and verify"
```

---

## Self-Review

### Spec Coverage

| Requirement (CLAUDE.md §6) | Task |
|---|---|
| Three generators: llms.txt, schema.json, robots.txt | Task 2 (service) + Task 4 (API) |
| Claude API powers llms.txt and schema.json | Task 2 |
| robots.txt allows GPTBot, PerplexityBot, ClaudeBot, Google-Extended | Task 2 |
| Copy button per file | Task 6 (ToolkitClient) |
| Download button per file | Task 6 (ToolkitClient) |
| Plain English implementation instructions per file | Task 6 (FILE_META.instruction) |
| Verification crawler checks domain URLs | Task 3 (crawler service) + Task 4 (API) |
| On verified: auto-update Technical Foundations score | Task 4 (/verify endpoint updates client.technical_foundations_verified) |
| On verified: auto-update Structured Data score | Task 4 (/verify endpoint updates client.structured_data_verified) |
| Files stored — not regenerated on every page load | Task 1 (DB model) + Task 4 (GET /files) + Task 6 (page fetches initialFiles) |

### Type Consistency Check

- `ToolkitFiles` type in `frontend/src/types/index.ts` fields match `ToolkitFilesResponse` schema in `backend/app/schemas/toolkit.py` ✓
- `VerificationResult` matches across frontend types and backend schema ✓
- `getToolkitFiles`, `generateToolkitFiles`, `verifyToolkitFiles` in `api.ts` use types defined in `index.ts` ✓
- `generate_toolkit_files` called in `toolkit.py` API is imported from `toolkit_service.py` ✓
- `verify_all` called in `toolkit.py` API is imported from `verification_crawler.py` ✓
- `_anthropic_client` function name used in test patches matches the function defined in `toolkit_service.py` ✓

### No Placeholders

Checked — no TBD/TODO/similar in the plan. All steps contain actual code.
