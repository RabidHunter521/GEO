# SeenBy Plan 1: Core Scan Engine + GEO Scoring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a FastAPI backend + Celery worker that accepts a scan trigger, calls Gemini 2.0 Flash with static query templates, detects brand mentions via string search, computes AI Citability and GEO scores, and persists all results to Supabase.

**Architecture:** FastAPI routes are thin — they validate input and enqueue a Celery task. The `scan_tasks.py` Celery task calls `scan_service.py` which orchestrates Gemini calls via `gemini_client.py`, brand detection via `brand_detection.py`, query building via `query_builder.py`, and score computation via `scoring_service.py`. All business logic is in services; nothing lives in routes or tasks. Supabase PostgreSQL is the database, accessed via SQLAlchemy 2 + Alembic.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2, Alembic, Celery 5 + Redis, google-generativeai, pydantic-settings 2, pytest, pytest-mock

---

## File Map

```
backend/
├── app/
│   ├── main.py                        # FastAPI app instance, router registration
│   ├── core/
│   │   ├── config.py                  # pydantic Settings — reads from .env
│   │   ├── constants.py               # SCORE_BANDS, SCORE_WEIGHTS, QUERY_TEMPLATES, etc.
│   │   └── database.py                # SQLAlchemy engine + get_db session dependency
│   ├── models/
│   │   ├── base.py                    # DeclarativeBase
│   │   ├── client.py                  # Client ORM model
│   │   ├── competitor.py              # Competitor ORM model
│   │   ├── scan.py                    # Scan ORM model
│   │   ├── scan_query_result.py       # ScanQueryResult ORM model
│   │   ├── geo_score.py               # GeoScore ORM model
│   │   └── activity_log.py            # ActivityLog ORM model (table only; UI in Plan 5)
│   ├── schemas/
│   │   └── scan.py                    # Pydantic request/response schemas for scan API
│   ├── api/v1/
│   │   ├── router.py                  # APIRouter that includes all v1 sub-routers
│   │   └── scans.py                   # POST /scans, GET /scans/{scan_id}
│   └── services/
│       ├── brand_detection.py         # detect_brand_mention(response_text, brand_name) -> bool
│       ├── query_builder.py           # build_client_queries(), build_competitor_queries()
│       ├── gemini_client.py           # GeminiClient.query(prompt) -> str
│       ├── scoring_service.py         # compute_ai_citability(), compute_geo_score(), get_score_band()
│       └── scan_service.py            # run_scan(scan_id, db) — full scan orchestration
├── workers/
│   ├── celery_app.py                  # Celery app instance + config
│   └── tasks/
│       └── scan_tasks.py              # execute_scan(scan_id) Celery task
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── conftest.py                    # SQLite in-memory DB fixture, test client
│   ├── test_brand_detection.py
│   ├── test_query_builder.py
│   ├── test_gemini_client.py
│   ├── test_scoring_service.py
│   ├── test_scan_service.py
│   └── test_api_scans.py
├── alembic.ini
├── pyproject.toml
└── .env.example
```

---

## Task 1: Backend Project Scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/alembic.ini`

- [ ] **Step 1: Create the backend directory and pyproject.toml**

```toml
# backend/pyproject.toml
[tool.poetry]
name = "seenby-backend"
version = "0.1.0"
description = "SeenBy backend API and workers"
authors = ["Faris <farisirfanyaakob@gmail.com>"]
packages = [{include = "app"}, {include = "workers"}]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}
sqlalchemy = "^2.0"
alembic = "^1.14"
celery = {extras = ["redis"], version = "^5.4"}
redis = "^5.2"
google-generativeai = "^0.8"
pydantic-settings = "^2.6"
psycopg2-binary = "^2.9"
structlog = "^24.4"
python-dotenv = "^1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-mock = "^3.14"
httpx = "^0.28"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create .env.example**

```bash
# backend/.env.example
DATABASE_URL=postgresql://postgres:[password]@[project].supabase.co:5432/postgres
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your_gemini_api_key_here
ADMIN_JWT_SECRET=change_me_to_a_random_32_char_string
```

- [ ] **Step 3: Create alembic.ini**

```ini
# backend/alembic.ini
[alembic]
script_location = alembic
file_template = %%(rev)s_%%(slug)s
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Install dependencies and verify**

```bash
cd backend
poetry install
```

Expected: Dependencies install without errors.

- [ ] **Step 5: Create all empty `__init__.py` files**

```bash
mkdir -p app/core app/models app/schemas app/api/v1 app/services workers/tasks alembic/versions tests
touch app/__init__.py app/core/__init__.py app/models/__init__.py
touch app/schemas/__init__.py app/api/__init__.py app/api/v1/__init__.py
touch app/services/__init__.py workers/__init__.py workers/tasks/__init__.py tests/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "chore: scaffold backend project structure"
```

---

## Task 2: Core Config + Database Setup

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/.env` (from .env.example — not committed)

- [ ] **Step 1: Create config.py**

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: str
    ADMIN_JWT_SECRET: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
```

- [ ] **Step 2: Create database.py**

```python
# backend/app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: Copy .env.example to .env and fill in your real values**

```bash
cp .env.example .env
# Edit .env with real Supabase URL, Gemini API key, Redis URL
```

Add `.env` to `.gitignore`:
```
# backend/.gitignore
.env
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py app/core/database.py .gitignore
git commit -m "chore: add settings and database session setup"
```

---

## Task 3: Constants

**Files:**
- Create: `backend/app/core/constants.py`

- [ ] **Step 1: Write constants.py**

```python
# backend/app/core/constants.py
from typing import Final

SCORE_VERSION: Final = "v1.0.0"

SCORE_WEIGHTS: Final = {
    "ai_citability":         0.40,
    "brand_authority":       0.20,
    "content_quality":       0.20,
    "technical_foundations": 0.10,
    "structured_data":       0.10,
}

SCORE_BANDS: Final = {
    "excellent":  (80, 100),
    "good":       (65, 79),
    "fair":       (50, 64),
    "developing": (35, 49),
    "low":        (0,  34),
}

SCORE_COLORS: Final = {
    "excellent":  "green",
    "good":       "green",
    "fair":       "yellow",
    "developing": "yellow",
    "low":        "red",
}

# Static query templates per category. {brand}, {competitor}, {industry}, {location}, {city} are filled at runtime.
QUERY_TEMPLATES: Final = {
    "brand": [
        "Tell me about {brand}",
        "What is {brand} known for?",
    ],
    "comparison": [
        "{brand} vs {competitor}",
        "Compare {brand} and {competitor}",
    ],
    "recommendation": [
        "Best {industry} in {location}",
        "Top {industry} in {location}",
    ],
    "local": [
        "Best {industry} near me in {city}",
        "{industry} services in {city}",
    ],
}

# Competitor query templates (4 per competitor, 1 per category)
COMPETITOR_QUERY_TEMPLATES: Final = {
    "brand":          "Tell me about {competitor}",
    "comparison":     "{competitor} vs {brand}",
    "recommendation": "Best {industry} company in {location}",
    "local":          "Top {industry} in {city}",
}

RAW_RESPONSE_RETENTION_DAYS: Final = 90
MAX_COMPETITORS: Final = 5
PLATFORM_GEMINI: Final = "gemini"
```

- [ ] **Step 2: Commit**

```bash
git add app/core/constants.py
git commit -m "chore: add score bands, weights, and query template constants"
```

---

## Task 4: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/client.py`
- Create: `backend/app/models/competitor.py`
- Create: `backend/app/models/scan.py`
- Create: `backend/app/models/scan_query_result.py`
- Create: `backend/app/models/geo_score.py`
- Create: `backend/app/models/activity_log.py`

- [ ] **Step 1: Create base.py**

```python
# backend/app/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Create client.py**

```python
# backend/app/models/client.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_authority_score: Mapped[int] = mapped_column(Integer, default=0)
    content_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    technical_foundations_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    structured_data_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    score_drop_threshold: Mapped[int] = mapped_column(Integer, default=35)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 3: Create competitor.py**

```python
# backend/app/models/competitor.py
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: Create scan.py**

```python
# backend/app/models/scan.py
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), default="gemini")
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending/running/completed/failed
    triggered_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 5: Create scan_query_result.py**

```python
# backend/app/models/scan_query_result.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ScanQueryResult(Base):
    __tablename__ = "scan_query_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # brand/comparison/recommendation/local
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # purged after 90 days
    brand_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

- [ ] **Step 6: Create geo_score.py**

```python
# backend/app/models/geo_score.py
import uuid
from datetime import datetime
from sqlalchemy import Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class GeoScore(Base):
    __tablename__ = "geo_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    ai_citability: Mapped[float] = mapped_column(Float, default=0.0)
    brand_authority: Mapped[float] = mapped_column(Float, default=0.0)
    content_quality: Mapped[float] = mapped_column(Float, default=0.0)
    technical_foundations: Mapped[float] = mapped_column(Float, default=0.0)
    structured_data: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

- [ ] **Step 7: Create activity_log.py**

```python
# backend/app/models/activity_log.py
import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

- [ ] **Step 8: Commit**

```bash
git add app/models/
git commit -m "feat: add SQLAlchemy ORM models for all core entities"
```

---

## Task 5: Alembic Migration

**Files:**
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py` (auto-generated)

- [ ] **Step 1: Create alembic/env.py**

```python
# backend/alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.core.config import settings
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 2: Generate the initial migration**

```bash
cd backend
poetry run alembic revision --autogenerate -m "initial_schema"
```

Expected: Creates a new file under `alembic/versions/` with `upgrade()` and `downgrade()` functions containing all table definitions.

- [ ] **Step 3: Run the migration against Supabase**

```bash
poetry run alembic upgrade head
```

Expected: `Running upgrade -> <rev>, initial_schema` with no errors. Verify tables exist in Supabase dashboard.

- [ ] **Step 4: Commit**

```bash
git add alembic/
git commit -m "feat: add initial Alembic schema migration"
```

---

## Task 6: Brand Detection + Query Builder (TDD)

**Files:**
- Create: `backend/app/services/brand_detection.py`
- Create: `backend/app/services/query_builder.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_brand_detection.py`
- Create: `backend/tests/test_query_builder.py`

- [ ] **Step 1: Create conftest.py with SQLite in-memory DB fixture**

```python
# backend/tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log  # noqa: F401


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # SQLite doesn't support UUID natively — use String instead for tests
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
```

> **Note:** The SQLite fixture works for most tests. For tests that require UUID columns behave as PostgreSQL UUIDs, create objects manually and avoid relying on PostgreSQL-specific behavior.

- [ ] **Step 2: Write failing tests for brand detection**

```python
# backend/tests/test_brand_detection.py
from app.services.brand_detection import detect_brand_mention


def test_exact_match_returns_true():
    assert detect_brand_mention("ACME Corp is a great company.", "ACME Corp") is True


def test_case_insensitive_match():
    assert detect_brand_mention("acme corp is mentioned here.", "ACME Corp") is True


def test_no_match_returns_false():
    assert detect_brand_mention("Some other company is great.", "ACME Corp") is False


def test_partial_word_not_matched():
    # "ACME" should not match brand "ACME Corp"
    assert detect_brand_mention("ACME is a word.", "ACME Corp") is False


def test_empty_response_returns_false():
    assert detect_brand_mention("", "ACME Corp") is False
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend
poetry run pytest tests/test_brand_detection.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.brand_detection'`

- [ ] **Step 4: Implement brand_detection.py**

```python
# backend/app/services/brand_detection.py


def detect_brand_mention(response_text: str, brand_name: str) -> bool:
    if not response_text or not brand_name:
        return False
    return brand_name.lower() in response_text.lower()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_brand_detection.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 6: Write failing tests for query builder**

```python
# backend/tests/test_query_builder.py
import pytest
from unittest.mock import MagicMock
from app.services.query_builder import build_client_queries, build_competitor_queries


def make_client(name="ACME Corp", industry="consulting", city="Kuala Lumpur", state="WP"):
    client = MagicMock()
    client.name = name
    client.industry = industry
    client.city = city
    client.state = state
    return client


def make_competitor(name="Rival Co"):
    comp = MagicMock()
    comp.id = "comp-id-1"
    comp.name = name
    return comp


def test_client_queries_returns_8_when_two_competitors():
    client = make_client()
    competitors = [make_competitor("Rival Co"), make_competitor("Other Co")]
    queries = build_client_queries(client, competitors)
    assert len(queries) == 8


def test_client_queries_returns_6_when_no_competitors():
    client = make_client()
    queries = build_client_queries(client, [])
    assert len(queries) == 6


def test_client_queries_contain_brand_name():
    client = make_client()
    queries = build_client_queries(client, [])
    brand_queries = [q for q in queries if q["category"] == "brand"]
    assert all("ACME Corp" in q["query_text"] for q in brand_queries)


def test_client_queries_competitor_id_is_none():
    client = make_client()
    competitors = [make_competitor()]
    queries = build_client_queries(client, competitors)
    assert all(q["competitor_id"] is None for q in queries)


def test_competitor_queries_returns_4_per_competitor():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    assert len(queries) == 4


def test_competitor_queries_set_competitor_id():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    assert all(q["competitor_id"] == comp.id for q in queries)


def test_competitor_queries_cover_all_categories():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    categories = {q["category"] for q in queries}
    assert categories == {"brand", "comparison", "recommendation", "local"}
```

- [ ] **Step 7: Run tests to verify they fail**

```bash
poetry run pytest tests/test_query_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.query_builder'`

- [ ] **Step 8: Implement query_builder.py**

```python
# backend/app/services/query_builder.py
from app.core.constants import QUERY_TEMPLATES, COMPETITOR_QUERY_TEMPLATES


def build_client_queries(client, competitors: list) -> list[dict]:
    queries = []
    location = f"{client.city}, {client.state}" if client.state else client.city

    for template in QUERY_TEMPLATES["brand"]:
        queries.append({
            "category": "brand",
            "query_text": template.format(brand=client.name),
            "competitor_id": None,
        })

    # Only add comparison queries if at least one competitor exists
    for i, template in enumerate(QUERY_TEMPLATES["comparison"]):
        if i < len(competitors):
            queries.append({
                "category": "comparison",
                "query_text": template.format(brand=client.name, competitor=competitors[i].name),
                "competitor_id": None,
            })

    for template in QUERY_TEMPLATES["recommendation"]:
        queries.append({
            "category": "recommendation",
            "query_text": template.format(industry=client.industry, location=location),
            "competitor_id": None,
        })

    for template in QUERY_TEMPLATES["local"]:
        queries.append({
            "category": "local",
            "query_text": template.format(industry=client.industry, city=client.city),
            "competitor_id": None,
        })

    return queries


def build_competitor_queries(client, competitor) -> list[dict]:
    location = f"{client.city}, {client.state}" if client.state else client.city
    return [
        {
            "category": "brand",
            "query_text": COMPETITOR_QUERY_TEMPLATES["brand"].format(competitor=competitor.name),
            "competitor_id": competitor.id,
        },
        {
            "category": "comparison",
            "query_text": COMPETITOR_QUERY_TEMPLATES["comparison"].format(
                competitor=competitor.name, brand=client.name
            ),
            "competitor_id": competitor.id,
        },
        {
            "category": "recommendation",
            "query_text": COMPETITOR_QUERY_TEMPLATES["recommendation"].format(
                industry=client.industry, location=location
            ),
            "competitor_id": competitor.id,
        },
        {
            "category": "local",
            "query_text": COMPETITOR_QUERY_TEMPLATES["local"].format(
                industry=client.industry, city=client.city
            ),
            "competitor_id": competitor.id,
        },
    ]
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
poetry run pytest tests/test_brand_detection.py tests/test_query_builder.py -v
```

Expected: All 12 tests PASSED.

- [ ] **Step 10: Commit**

```bash
git add app/services/brand_detection.py app/services/query_builder.py tests/
git commit -m "feat: add brand detection and query builder with tests"
```

---

## Task 7: Gemini Client (TDD with Mock)

**Files:**
- Create: `backend/app/services/gemini_client.py`
- Create: `backend/tests/test_gemini_client.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_gemini_client.py
from unittest.mock import patch, MagicMock
from app.services.gemini_client import GeminiClient


def test_query_returns_text_response():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp is a leading consulting firm in KL."

    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp is a leading consulting firm in KL."


def test_query_retries_on_exception_then_succeeds():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp response."

    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [Exception("API error"), mock_response]
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp response."
    assert mock_model.generate_content.call_count == 2


def test_query_raises_after_two_failures():
    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API error")
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(api_key="fake-key")
        try:
            client.query("Tell me about ACME Corp")
            assert False, "Should have raised"
        except Exception as e:
            assert "API error" in str(e)

    assert mock_model.generate_content.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_gemini_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.gemini_client'`

- [ ] **Step 3: Implement gemini_client.py**

```python
# backend/app/services/gemini_client.py
import google.generativeai as genai
import structlog

logger = structlog.get_logger()

MODEL_NAME = "gemini-2.0-flash"


class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(MODEL_NAME)

    def query(self, prompt: str) -> str:
        last_exc = None
        for attempt in range(2):
            try:
                response = self._model.generate_content(prompt)
                return response.text
            except Exception as exc:
                last_exc = exc
                logger.warning("gemini_query_failed", attempt=attempt + 1, error=str(exc))
        raise last_exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_gemini_client.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/services/gemini_client.py tests/test_gemini_client.py
git commit -m "feat: add Gemini client with retry logic and tests"
```

---

## Task 8: GEO Scoring Service (TDD)

**Files:**
- Create: `backend/app/services/scoring_service.py`
- Create: `backend/tests/test_scoring_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_scoring_service.py
from unittest.mock import MagicMock
from app.services.scoring_service import (
    compute_ai_citability,
    compute_geo_score,
    get_score_band,
)


def test_citability_all_detected():
    results = [MagicMock(brand_detected=True, competitor_id=None) for _ in range(8)]
    assert compute_ai_citability(results) == 100.0


def test_citability_none_detected():
    results = [MagicMock(brand_detected=False, competitor_id=None) for _ in range(8)]
    assert compute_ai_citability(results) == 0.0


def test_citability_half_detected():
    results = (
        [MagicMock(brand_detected=True, competitor_id=None) for _ in range(4)]
        + [MagicMock(brand_detected=False, competitor_id=None) for _ in range(4)]
    )
    assert compute_ai_citability(results) == 50.0


def test_citability_ignores_competitor_queries():
    # competitor_id is set → these are competitor queries, not client queries
    client_results = [MagicMock(brand_detected=True, competitor_id=None) for _ in range(4)]
    competitor_results = [MagicMock(brand_detected=False, competitor_id="some-id") for _ in range(4)]
    assert compute_ai_citability(client_results + competitor_results) == 100.0


def test_geo_score_full_weights():
    client = MagicMock(
        brand_authority_score=80,
        content_quality_score=70,
        technical_foundations_verified=True,
        structured_data_verified=True,
    )
    score = compute_geo_score(client, ai_citability=100.0)
    expected = (100.0 * 0.40) + (80 * 0.20) + (70 * 0.20) + (100 * 0.10) + (100 * 0.10)
    assert abs(score - expected) < 0.001


def test_geo_score_unverified_toolkit_contributes_zero():
    client = MagicMock(
        brand_authority_score=0,
        content_quality_score=0,
        technical_foundations_verified=False,
        structured_data_verified=False,
    )
    score = compute_geo_score(client, ai_citability=50.0)
    assert score == 50.0 * 0.40


def test_get_score_band_excellent():
    assert get_score_band(95) == ("excellent", "green")


def test_get_score_band_good():
    assert get_score_band(70) == ("good", "green")


def test_get_score_band_fair():
    assert get_score_band(55) == ("fair", "yellow")


def test_get_score_band_developing():
    assert get_score_band(40) == ("developing", "yellow")


def test_get_score_band_low():
    assert get_score_band(20) == ("low", "red")


def test_get_score_band_boundary_80():
    assert get_score_band(80) == ("excellent", "green")


def test_get_score_band_boundary_65():
    assert get_score_band(65) == ("good", "green")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_scoring_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.scoring_service'`

- [ ] **Step 3: Implement scoring_service.py**

```python
# backend/app/services/scoring_service.py
from app.core.constants import SCORE_BANDS, SCORE_COLORS, SCORE_WEIGHTS


def compute_ai_citability(query_results: list) -> float:
    """Compute AI Citability score from client query results only (competitor_id is None)."""
    client_results = [r for r in query_results if r.competitor_id is None]
    if not client_results:
        return 0.0
    detected = sum(1 for r in client_results if r.brand_detected)
    return round((detected / len(client_results)) * 100, 2)


def compute_geo_score(client, ai_citability: float) -> float:
    """Compute overall GEO score from 5 weighted dimensions."""
    technical = 100.0 if client.technical_foundations_verified else 0.0
    structured = 100.0 if client.structured_data_verified else 0.0
    return round(
        ai_citability * SCORE_WEIGHTS["ai_citability"]
        + client.brand_authority_score * SCORE_WEIGHTS["brand_authority"]
        + client.content_quality_score * SCORE_WEIGHTS["content_quality"]
        + technical * SCORE_WEIGHTS["technical_foundations"]
        + structured * SCORE_WEIGHTS["structured_data"],
        2,
    )


def get_score_band(score: float) -> tuple[str, str]:
    """Return (band_name, color) for a given score."""
    for band, (low, high) in SCORE_BANDS.items():
        if low <= score <= high:
            return band, SCORE_COLORS[band]
    return "low", SCORE_COLORS["low"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_scoring_service.py -v
```

Expected: All 12 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/services/scoring_service.py tests/test_scoring_service.py
git commit -m "feat: add GEO scoring service with tests"
```

---

## Task 9: Scan Service (TDD)

**Files:**
- Create: `backend/app/services/scan_service.py`
- Create: `backend/tests/test_scan_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_scan_service.py
import uuid
from unittest.mock import MagicMock, patch
from app.services.scan_service import run_scan


def make_scan(scan_id=None, client_id=None):
    scan = MagicMock()
    scan.id = scan_id or uuid.uuid4()
    scan.client_id = client_id or uuid.uuid4()
    scan.status = "pending"
    scan.platform = "gemini"
    return scan


def make_client(name="ACME Corp"):
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = name
    client.industry = "consulting"
    client.city = "Kuala Lumpur"
    client.state = "WP"
    client.brand_authority_score = 50
    client.content_quality_score = 50
    client.technical_foundations_verified = False
    client.structured_data_verified = False
    return client


def test_run_scan_sets_status_to_completed(db):
    scan = make_scan()
    client = make_client()
    competitors = []

    db.add = MagicMock()
    db.commit = MagicMock()
    db.query = MagicMock()

    # Mock DB queries
    db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    db.query.return_value.filter.return_value.all.return_value = competitors

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.return_value = "ACME Corp is great."
        MockGemini.return_value = mock_gemini

        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            run_scan(scan.id, db)

    assert scan.status == "completed"


def test_run_scan_creates_geo_score_row(db):
    scan = make_scan()
    client = make_client()

    db.add = MagicMock()
    db.commit = MagicMock()
    db.query = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    db.query.return_value.filter.return_value.all.return_value = []

    added_objects = []
    db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.return_value = "ACME Corp mentioned."
        MockGemini.return_value = mock_gemini
        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            run_scan(scan.id, db)

    from app.models.geo_score import GeoScore
    geo_scores = [o for o in added_objects if isinstance(o, GeoScore)]
    assert len(geo_scores) == 1


def test_run_scan_sets_failed_on_gemini_error(db):
    scan = make_scan()
    client = make_client()

    db.add = MagicMock()
    db.commit = MagicMock()
    db.query = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.side_effect = Exception("Gemini unavailable")
        MockGemini.return_value = mock_gemini
        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            run_scan(scan.id, db)

    assert scan.status == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_scan_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.scan_service'`

- [ ] **Step 3: Implement scan_service.py**

```python
# backend/app/services/scan_service.py
import time
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.core.config import settings
from app.models.scan import Scan
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.services.gemini_client import GeminiClient
from app.services.brand_detection import detect_brand_mention
from app.services.query_builder import build_client_queries, build_competitor_queries
from app.services.scoring_service import compute_ai_citability, compute_geo_score

logger = structlog.get_logger()

_INTER_QUERY_DELAY_SECONDS = 0.5  # rate-limit buffer for Gemini free tier


def run_scan(scan_id: uuid.UUID, db: Session) -> None:
    scan: Scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        logger.error("scan_not_found", scan_id=str(scan_id))
        return

    scan.status = "running"
    db.commit()
    logger.info("scan_started", scan_id=str(scan_id))

    try:
        client: Client = db.query(Client).filter(Client.id == scan.client_id).first()
        competitors: list[Competitor] = (
            db.query(Competitor).filter(Competitor.client_id == scan.client_id).all()
        )
        gemini = GeminiClient(api_key=settings.GEMINI_API_KEY)

        # Run client queries
        client_queries = build_client_queries(client, competitors)
        for q in client_queries:
            response_text = gemini.query(q["query_text"])
            detected = detect_brand_mention(response_text, client.name)
            result = ScanQueryResult(
                scan_id=scan.id,
                competitor_id=None,
                category=q["category"],
                query_text=q["query_text"],
                response_text=response_text,
                brand_detected=detected,
            )
            db.add(result)
            time.sleep(_INTER_QUERY_DELAY_SECONDS)

        # Run competitor queries
        for competitor in competitors:
            comp_queries = build_competitor_queries(client, competitor)
            for q in comp_queries:
                response_text = gemini.query(q["query_text"])
                detected = detect_brand_mention(response_text, competitor.name)
                result = ScanQueryResult(
                    scan_id=scan.id,
                    competitor_id=competitor.id,
                    category=q["category"],
                    query_text=q["query_text"],
                    response_text=response_text,
                    brand_detected=detected,
                )
                db.add(result)
                time.sleep(_INTER_QUERY_DELAY_SECONDS)

        db.commit()

        # Compute and persist GEO score
        all_results = (
            db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scan.id).all()
        )
        ai_citability = compute_ai_citability(all_results)
        overall = compute_geo_score(client, ai_citability)

        geo_score = GeoScore(
            client_id=client.id,
            scan_id=scan.id,
            ai_citability=ai_citability,
            brand_authority=float(client.brand_authority_score),
            content_quality=float(client.content_quality_score),
            technical_foundations=100.0 if client.technical_foundations_verified else 0.0,
            structured_data=100.0 if client.structured_data_verified else 0.0,
            overall_score=overall,
        )
        db.add(geo_score)

        # Activity log entry
        db.add(ActivityLog(
            client_id=client.id,
            event_type="scan_completed",
            note=f"Scan completed. AI Citability: {ai_citability:.1f}. Overall GEO score: {overall:.1f}.",
        ))

        scan.status = "completed"
        scan.completed_at = datetime.utcnow()
        db.commit()
        logger.info("scan_completed", scan_id=str(scan_id), overall_score=overall)

    except Exception as exc:
        scan.status = "failed"
        db.commit()
        logger.error("scan_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
poetry run pytest tests/ -v
```

Expected: All tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/services/scan_service.py tests/test_scan_service.py
git commit -m "feat: add scan orchestration service with tests"
```

---

## Task 10: Celery Setup + Scan Task

**Files:**
- Create: `backend/workers/celery_app.py`
- Create: `backend/workers/tasks/scan_tasks.py`

- [ ] **Step 1: Create celery_app.py**

```python
# backend/workers/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "seenby",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks.scan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
```

- [ ] **Step 2: Create scan_tasks.py**

```python
# backend/workers/tasks/scan_tasks.py
import uuid
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.scan_service import run_scan

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.scan_tasks.execute_scan", bind=True)
def execute_scan(self, scan_id: str) -> dict:
    logger.info("execute_scan_task_started", scan_id=scan_id)
    db = SessionLocal()
    try:
        run_scan(uuid.UUID(scan_id), db)
        return {"status": "completed", "scan_id": scan_id}
    finally:
        db.close()
```

- [ ] **Step 3: Start Redis locally and verify Celery worker starts**

```bash
# In one terminal — start Redis (Docker)
docker run -p 6379:6379 redis:alpine

# In another terminal — start Celery worker
cd backend
poetry run celery -A workers.celery_app worker --loglevel=info
```

Expected: Worker starts and shows `[tasks]` list including `workers.tasks.scan_tasks.execute_scan`.

- [ ] **Step 4: Commit**

```bash
git add workers/
git commit -m "feat: add Celery app and execute_scan task"
```

---

## Task 11: FastAPI App + Scan API

**Files:**
- Create: `backend/app/schemas/scan.py`
- Create: `backend/app/api/v1/scans.py`
- Create: `backend/app/api/v1/router.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api_scans.py`

- [ ] **Step 1: Create scan schemas**

```python
# backend/app/schemas/scan.py
import uuid
from datetime import datetime
from pydantic import BaseModel


class TriggerScanRequest(BaseModel):
    client_id: uuid.UUID


class ScanResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    platform: str
    status: str
    triggered_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create scan API route**

```python
# backend/app/api/v1/scans.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scan import Scan
from app.schemas.scan import TriggerScanRequest, ScanResponse

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/", response_model=ScanResponse, status_code=202)
def trigger_scan(payload: TriggerScanRequest, db: Session = Depends(get_db)):
    from workers.tasks.scan_tasks import execute_scan

    scan = Scan(client_id=payload.client_id)
    db.add(scan)
    db.commit()
    db.refresh(scan)

    execute_scan.delay(str(scan.id))
    return scan


@router.get("/{scan_id}", response_model=ScanResponse)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
```

- [ ] **Step 3: Create API router**

```python
# backend/app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import scans

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
```

- [ ] **Step 4: Create main.py**

```python
# backend/app/main.py
from fastapi import FastAPI
from app.api.v1.router import router

app = FastAPI(title="SeenBy API", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write API tests**

```python
# backend/tests/test_api_scans.py
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_scan_returns_202():
    with patch("app.api.v1.scans.get_db") as mock_get_db, \
         patch("app.api.v1.scans.execute_scan") as mock_task:

        mock_db = MagicMock()
        mock_scan = MagicMock()
        mock_scan.id = uuid.uuid4()
        mock_scan.client_id = uuid.uuid4()
        mock_scan.platform = "gemini"
        mock_scan.status = "pending"
        mock_scan.triggered_at = "2026-01-01T00:00:00"
        mock_scan.completed_at = None
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock(side_effect=lambda s: None)
        mock_get_db.return_value = iter([mock_db])

        mock_task.delay = MagicMock()

        # Override dependency
        from app.core.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.post("/api/v1/scans/", json={"client_id": str(uuid.uuid4())})
        assert response.status_code in (200, 201, 202)

        app.dependency_overrides.clear()


def test_get_scan_not_found():
    with patch("app.api.v1.scans.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from app.core.database import get_db
        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(f"/api/v1/scans/{uuid.uuid4()}")
        assert response.status_code == 404

        app.dependency_overrides.clear()
```

- [ ] **Step 6: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: All tests PASSED.

- [ ] **Step 7: Start the API server and verify it runs**

```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

Open: `http://localhost:8000/health` → `{"status": "ok"}`
Open: `http://localhost:8000/docs` → Swagger UI showing `/api/v1/scans/` endpoints.

- [ ] **Step 8: Commit**

```bash
git add app/schemas/ app/api/ app/main.py tests/test_api_scans.py
git commit -m "feat: add FastAPI scan endpoints with tests"
```

---

## Task 12: End-to-End Smoke Test

This task runs manually with a real Supabase DB, real Gemini API, and real Redis/Celery.

- [ ] **Step 1: Insert a test client into Supabase**

Use Supabase Table Editor or run:

```sql
INSERT INTO clients (id, name, website, industry, city, state, created_at)
VALUES (
  gen_random_uuid(),
  'Test Brand',
  'https://testbrand.com',
  'consulting',
  'Kuala Lumpur',
  'WP',
  NOW()
);
```

Copy the generated `id`.

- [ ] **Step 2: Ensure Redis + Celery worker are running**

```bash
# Terminal 1
docker run -p 6379:6379 redis:alpine

# Terminal 2
cd backend
poetry run celery -A workers.celery_app worker --loglevel=info
```

- [ ] **Step 3: Start the API server**

```bash
# Terminal 3
poetry run uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 4: Trigger a scan via the API**

```bash
curl -X POST http://localhost:8000/api/v1/scans/ \
  -H "Content-Type: application/json" \
  -d '{"client_id": "<paste-client-id-here>"}'
```

Expected response (202): `{"id": "...", "status": "pending", ...}`

Copy the scan `id` from the response.

- [ ] **Step 5: Poll scan status**

```bash
curl http://localhost:8000/api/v1/scans/<scan-id>
```

Repeat every 30 seconds. Expected final status: `"completed"` (scan with 6–28 Gemini calls takes 1–3 minutes on free tier).

- [ ] **Step 6: Verify results in Supabase**

In Supabase Table Editor, check:
- `scan_query_results` — rows with `brand_detected` true/false
- `geo_scores` — one row with `overall_score` computed
- `activity_log` — one row with `event_type = "scan_completed"`

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: complete scan engine + GEO scoring — Plan 1 done"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| 8 queries per scan, 2 per category × 4 categories | Task 6 (query_builder) |
| 4 queries per competitor | Task 6 (build_competitor_queries) |
| Gemini 2.0 Flash, free tier | Task 7 (gemini_client) |
| Retry once on API failure | Task 7 (GeminiClient.query) |
| Brand detection via string search | Task 6 (brand_detection) |
| AI Citability = detected/total × 100 | Task 8 (scoring_service) |
| GEO score 5-dimension weighted sum | Task 8 (compute_geo_score) |
| Score bands + colors | Task 8 (get_score_band) |
| Store raw responses | Task 9 (scan_service, response_text field) |
| Platform field on every result | Task 4 (scan model), Task 9 |
| Activity log entry on scan complete | Task 9 (scan_service) |
| SCORE_VERSION constant | Task 3 (constants.py) |
| Comparison queries skip if no competitors | Task 6 (query_builder) |
| Score drop threshold per client | Task 4 (client model — alerts handled in Plan 8) |

**No placeholders found.**

**Type consistency verified** — `ScanQueryResult`, `GeoScore`, `ActivityLog`, `Client`, `Competitor`, `Scan` names used consistently across models, services, and tests.
