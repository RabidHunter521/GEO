# Monthly PDF Report Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate a branded monthly AI Visibility PDF report per client using WeasyPrint, store it in Cloudflare R2, and let Faris review + manually trigger email delivery via a Reports page in the admin panel.

**Architecture:** A `report_service` gathers scan data (latest completed scan within 30 days), builds an HTML document, renders it to PDF via WeasyPrint, uploads to Cloudflare R2 (S3-compatible), and saves a `Report` record (key + URL, no PDF bytes in Postgres). A daily Celery Beat task checks which clients are due for a report (30 days since signup or 30 days since last report). The admin sees all reports in the `/clients/[id]/reports` page, downloads the PDF for review, then clicks "Send to Client" which emails the PDF as an attachment via Resend.

**Tech Stack:** WeasyPrint (PDF), boto3 (R2 upload/download), Resend (email with PDF attachment), FastAPI, SQLAlchemy, Alembic, Celery Beat, Next.js 15 + shadcn/ui

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/app/models/report.py` | Report ORM model |
| Create | `backend/app/schemas/report.py` | ReportResponse Pydantic schema |
| Create | `backend/app/services/r2_service.py` | R2 upload + download via boto3 |
| Create | `backend/app/services/report_service.py` | PDF generation, data gathering, email send |
| Create | `backend/app/api/v1/reports.py` | API routes: generate, list, send |
| Create | `backend/workers/tasks/report_tasks.py` | Celery tasks: generate one, check all due |
| Create | `backend/tests/test_r2_service.py` | Unit tests for R2 service |
| Create | `backend/tests/test_report_service.py` | Unit tests for report service logic |
| Create | `frontend/src/app/clients/[id]/reports/ReportsClient.tsx` | Client component: list + actions |
| Create | `frontend/src/app/clients/[id]/reports/actions.ts` | Server actions: generate, send |
| Modify | `backend/pyproject.toml` | Add weasyprint, boto3 |
| Modify | `backend/app/core/config.py` | Add R2 settings |
| Modify | `backend/.env.example` | Document R2 env vars |
| Modify | `backend/alembic/env.py` | Import report model for autogenerate |
| Modify | `backend/app/api/v1/router.py` | Include reports router |
| Modify | `backend/workers/celery_app.py` | Include report_tasks + add Beat schedule |
| Modify | `backend/tests/conftest.py` | Import report model for in-memory DB |
| Modify | `frontend/src/types/index.ts` | Add Report interface |
| Modify | `frontend/src/lib/api.ts` | Add report API functions |
| Modify | `frontend/src/app/clients/[id]/reports/page.tsx` | Replace placeholder with ReportsClient |
| Modify | `frontend/src/app/clients/[id]/activity/page.tsx` | Add report_generated + report_sent labels |

---

## Task 1: Install WeasyPrint + boto3

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Open `backend/pyproject.toml`. In `[tool.poetry.dependencies]`, add after the `resend` line:

```toml
weasyprint = "^62"
boto3 = "^1.35"
```

- [ ] **Step 2: Install**

```bash
cd backend
poetry add weasyprint boto3
```

Expected: both packages resolve and install without error.

- [ ] **Step 3: Verify import works**

```bash
poetry run python -c "import weasyprint; import boto3; print('ok')"
```

Expected: prints `ok` with no error.

> **Note — WeasyPrint system dependencies:**
> WeasyPrint requires Pango + Cairo at runtime. On Ubuntu/Debian Docker images add:
> `apt-get install -y libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0`
> On macOS dev machines: `brew install pango`
> On Windows (dev only): install the GTK3 runtime from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/poetry.lock
git commit -m "feat: add weasyprint and boto3 for PDF generation and R2 upload"
```

---

## Task 2: R2 Config + .env.example

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add R2 settings to Settings class**

In `backend/app/core/config.py`, add these five fields inside the `Settings` class after `RESEND_API_KEY`:

```python
CLOUDFLARE_R2_ENDPOINT_URL: str = ""
CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
CLOUDFLARE_R2_BUCKET_NAME: str = "seenby-reports"
CLOUDFLARE_R2_PUBLIC_URL: str = ""
```

The full class becomes:

```python
class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: str
    ADMIN_JWT_SECRET: str
    ADMIN_API_KEY: str
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    ANTHROPIC_API_KEY: str
    RESEND_API_KEY: str
    CLOUDFLARE_R2_ENDPOINT_URL: str = ""
    CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
    CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
    CLOUDFLARE_R2_BUCKET_NAME: str = "seenby-reports"
    CLOUDFLARE_R2_PUBLIC_URL: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

- [ ] **Step 2: Update .env.example**

Append to `backend/.env.example`:

```
CLOUDFLARE_R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
CLOUDFLARE_R2_ACCESS_KEY_ID=your_r2_access_key_id
CLOUDFLARE_R2_SECRET_ACCESS_KEY=your_r2_secret_access_key
CLOUDFLARE_R2_BUCKET_NAME=seenby-reports
CLOUDFLARE_R2_PUBLIC_URL=https://pub.r2.dev/<bucket_name>
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py backend/.env.example
git commit -m "feat: add Cloudflare R2 config settings"
```

---

## Task 3: Create Report Model

**Files:**
- Create: `backend/app/models/report.py`

- [ ] **Step 1: Create the model**

Create `backend/app/models/report.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    r2_key: Mapped[str] = mapped_column(String(512), nullable=False)
    r2_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/report.py
git commit -m "feat: add Report ORM model"
```

---

## Task 4: Alembic Migration

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/<hash>_create_reports_table.py` (autogenerated)

- [ ] **Step 1: Add report model import to alembic/env.py**

In `backend/alembic/env.py`, add `report` to the existing model import line:

```python
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log, toolkit_files, report  # noqa: F401
```

- [ ] **Step 2: Generate migration**

```bash
cd backend
poetry run alembic revision --autogenerate -m "create_reports_table"
```

Expected: a new file appears in `backend/alembic/versions/` — open it and confirm it contains `op.create_table("reports", ...)` with columns `id`, `client_id`, `r2_key`, `r2_url`, `period_start`, `period_end`, `overall_score`, `generated_at`, `sent_at`.

- [ ] **Step 3: Apply migration**

```bash
poetry run alembic upgrade head
```

Expected: `Running upgrade ... -> <hash>, create_reports_table` with no errors.

- [ ] **Step 4: Update conftest.py to include report model**

In `backend/tests/conftest.py`, add `report` to the model import so the in-memory SQLite DB knows about the `reports` table:

```python
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log, toolkit_files, report  # noqa: F401
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/env.py backend/alembic/versions/ backend/tests/conftest.py
git commit -m "feat: add Alembic migration for reports table"
```

---

## Task 5: R2 Service (TDD)

**Files:**
- Create: `backend/app/services/r2_service.py`
- Create: `backend/tests/test_r2_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_r2_service.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


def _patch_settings(**kwargs):
    defaults = dict(
        CLOUDFLARE_R2_ENDPOINT_URL="https://acct.r2.cloudflarestorage.com",
        CLOUDFLARE_R2_ACCESS_KEY_ID="key123",
        CLOUDFLARE_R2_SECRET_ACCESS_KEY="secret456",
        CLOUDFLARE_R2_BUCKET_NAME="seenby-reports",
        CLOUDFLARE_R2_PUBLIC_URL="https://pub.seenby.my",
    )
    defaults.update(kwargs)
    return defaults


def test_upload_pdf_calls_put_object_with_correct_args():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", **_patch_settings()):
        from app.services.r2_service import upload_pdf
        upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    mock_s3.put_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
        Body=b"pdfdata",
        ContentType="application/pdf",
    )


def test_upload_pdf_returns_public_url():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", **_patch_settings()):
        from app.services.r2_service import upload_pdf
        url = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert url == "https://pub.seenby.my/reports/abc/20260601.pdf"


def test_upload_pdf_strips_trailing_slash_from_public_url():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", **_patch_settings(CLOUDFLARE_R2_PUBLIC_URL="https://pub.seenby.my/")):
        from app.services.r2_service import upload_pdf
        url = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert url == "https://pub.seenby.my/reports/abc/20260601.pdf"


def test_download_pdf_returns_bytes_from_s3():
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"pdf-content")}
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", **_patch_settings()):
        from app.services.r2_service import download_pdf
        result = download_pdf("reports/abc/20260601.pdf")
    assert result == b"pdf-content"
    mock_s3.get_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
    )
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
poetry run pytest tests/test_r2_service.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `r2_service` does not exist yet.

- [ ] **Step 3: Implement r2_service.py**

Create `backend/app/services/r2_service.py`:

```python
import boto3
from botocore.config import Config
from app.core.config import settings


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT_URL,
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )


def upload_pdf(key: str, pdf_bytes: bytes) -> str:
    """Upload PDF bytes to R2; return public URL."""
    _s3().put_object(
        Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    return f"{settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')}/{key}"


def download_pdf(key: str) -> bytes:
    """Download PDF bytes from R2 by key."""
    resp = _s3().get_object(Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME, Key=key)
    return resp["Body"].read()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
poetry run pytest tests/test_r2_service.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/r2_service.py backend/tests/test_r2_service.py
git commit -m "feat: add R2 service for PDF upload and download"
```

---

## Task 6: Report Schemas

**Files:**
- Create: `backend/app/schemas/report.py`

- [ ] **Step 1: Create schema**

Create `backend/app/schemas/report.py`:

```python
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    r2_url: str
    period_start: datetime
    period_end: datetime
    overall_score: float
    generated_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/report.py
git commit -m "feat: add ReportResponse schema"
```

---

## Task 7: Report Service — Data Gathering + HTML Building (TDD)

**Files:**
- Create: `backend/app/services/report_service.py` (partial — dataclasses + `_gather_report_data` + `_build_report_html` + `_compute_trend`)
- Create: `backend/tests/test_report_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_report_service.py`:

```python
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ── _compute_trend ─────────────────────────────────────────────────────────────

def test_trend_up_when_overall_increases_more_than_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(72.0, 60.0) == "up"


def test_trend_down_when_overall_decreases_more_than_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(55.0, 70.0) == "down"


def test_trend_flat_within_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(60.3, 60.0) == "flat"


def test_trend_first_when_no_previous():
    from app.services.report_service import _compute_trend
    assert _compute_trend(50.0, None) == "first"


# ── _gather_report_data ────────────────────────────────────────────────────────

def test_gather_report_data_returns_none_when_no_recent_scan():
    from app.services.report_service import _gather_report_data
    client = MagicMock()
    client.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    assert _gather_report_data(client, db) is None


def test_gather_report_data_returns_none_when_no_geo_score():
    from app.services.report_service import _gather_report_data
    client = MagicMock()
    client.id = uuid.uuid4()
    db = MagicMock()
    mock_scan = MagicMock()
    mock_scan.id = uuid.uuid4()
    # first call (latest_scan) returns a scan; second call (GeoScore) returns None
    db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
        mock_scan,  # latest scan
        None,       # GeoScore
    ]
    assert _gather_report_data(client, db) is None


# ── _build_report_html ────────────────────────────────────────────────────────

def _make_report_data():
    from app.services.report_service import ReportData, CompetitorSummary
    return ReportData(
        period_start=datetime(2026, 5, 1),
        period_end=datetime(2026, 5, 31),
        period_label="May 2026",
        overall_score=72.5,
        score_band="good",
        score_color="green",
        ai_citability=75.0,
        brand_authority=60.0,
        content_quality=70.0,
        technical_foundations=100.0,
        structured_data=0.0,
        prev_overall_score=65.0,
        trend="up",
        seen_count=6,
        total_count=8,
        llms_verified=True,
        schema_verified=False,
        robots_verified=True,
        competitors=[CompetitorSummary(name="Rival Co", ai_citability=80.0, is_winning=True)],
        recommendation="Publish a blog post.",
    )


def test_build_report_html_contains_client_name():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Acme Corp" in html


def test_build_report_html_contains_period_label():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "May 2026" in html


def test_build_report_html_contains_overall_score():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "72" in html


def test_build_report_html_contains_all_required_sections():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "AI Visibility Score" in html
    assert "Score Breakdown" in html
    assert "AI Visibility Frequency" in html
    assert "Competitor Comparison" in html
    assert "AI Readiness Toolkit" in html
    assert "Recommended Action" in html


def test_build_report_html_shows_seen_count():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "6/8" in html


def test_build_report_html_shows_competitor():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Rival Co" in html


def test_build_report_html_shows_recommendation():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Publish a blog post." in html


def test_build_report_html_shows_toolkit_verified_status():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    # llms_verified=True, schema_verified=False
    assert html.count("Verified") >= 1
    assert "Not Verified" in html


def test_build_report_html_contains_manual_assessment_label():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Assessed by SeenBy team" in html
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd backend
poetry run pytest tests/test_report_service.py -v
```

Expected: `ImportError: cannot import name '_compute_trend' from 'app.services.report_service'`

- [ ] **Step 3: Implement partial report_service.py (dataclasses + functions under test)**

Create `backend/app/services/report_service.py`:

```python
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import structlog

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.competitor import Competitor
from app.models.toolkit_files import ToolkitFiles
from app.models.activity_log import ActivityLog
from app.models.report import Report
from app.services.scoring_service import get_score_band
from app.services.r2_service import upload_pdf, download_pdf
from app.services.claude_action import get_digest_action

logger = structlog.get_logger()

_CSS = """
@page {
  size: A4;
  margin: 2cm;
}
* { box-sizing: border-box; }
body {
  font-family: Arial, Helvetica, sans-serif;
  color: #1e293b;
  font-size: 11pt;
  line-height: 1.6;
  margin: 0;
}
.page-break { page-break-after: always; }
.cover { text-align: center; padding-top: 80px; }
.logo { font-size: 28pt; font-weight: 700; color: #0f172a; }
.cover-client { font-size: 22pt; font-weight: 700; color: #0f172a; margin-top: 60px; }
.cover-period { font-size: 13pt; color: #64748b; margin-top: 6px; }
.score-box {
  display: inline-block; background: #0f172a; color: #ffffff;
  border-radius: 12px; padding: 24px 56px; margin-top: 56px;
}
.score-box-value { font-size: 52pt; font-weight: 700; line-height: 1; }
.score-box-label { font-size: 11pt; color: #94a3b8; margin-top: 4px; }
.cover-footer { margin-top: 60px; font-size: 10pt; color: #94a3b8; }
h2 {
  font-size: 13pt; font-weight: 700; color: #0f172a;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 6px; margin-top: 28px; margin-bottom: 14px;
}
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
th {
  background: #f8fafc; padding: 8px 12px; text-align: left;
  font-weight: 600; color: #64748b; font-size: 9pt;
  text-transform: uppercase; letter-spacing: 0.05em;
  border-bottom: 1px solid #e2e8f0;
}
td { padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }
.score-green { color: #16a34a; font-weight: 600; }
.score-yellow { color: #ca8a04; font-weight: 600; }
.score-red { color: #dc2626; font-weight: 600; }
.badge-green { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.badge-yellow { background: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.badge-red { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.stat-box {
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;
}
.stat-label { font-size: 9pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { font-size: 24pt; font-weight: 700; color: #0f172a; line-height: 1.2; }
.stat-sub { font-size: 10pt; color: #64748b; margin-top: 4px; }
.rec-box { background: #f0f9ff; border-left: 4px solid #0284c7; padding: 14px 16px; border-radius: 4px; }
.manual-note { font-size: 8pt; color: #94a3b8; font-style: italic; margin-top: 2px; }
"""


@dataclass
class CompetitorSummary:
    name: str
    ai_citability: float
    is_winning: bool


@dataclass
class ReportData:
    period_start: datetime
    period_end: datetime
    period_label: str
    overall_score: float
    score_band: str
    score_color: str
    ai_citability: float
    brand_authority: float
    content_quality: float
    technical_foundations: float
    structured_data: float
    prev_overall_score: float | None
    trend: str
    seen_count: int
    total_count: int
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    competitors: list[CompetitorSummary] = field(default_factory=list)
    recommendation: str = ""


def _compute_trend(current: float, prev: float | None) -> str:
    if prev is None:
        return "first"
    if current > prev + 0.5:
        return "up"
    if current < prev - 0.5:
        return "down"
    return "flat"


def _score_css(color: str) -> str:
    return {"green": "score-green", "yellow": "score-yellow", "red": "score-red"}.get(color, "score-red")


def _verified_badge(verified: bool) -> str:
    return '<span class="badge-green">Verified</span>' if verified else '<span class="badge-red">Not Verified</span>'


def _gather_report_data(client: Client, db: Session) -> ReportData | None:
    since = datetime.utcnow() - timedelta(days=30)

    latest_scan: Scan | None = (
        db.query(Scan)
        .filter(
            Scan.client_id == client.id,
            Scan.status == "completed",
            Scan.completed_at >= since,
        )
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return None

    current_gs: GeoScore | None = (
        db.query(GeoScore).filter(GeoScore.scan_id == latest_scan.id).first()
    )
    if not current_gs:
        return None

    prev_scan: Scan | None = (
        db.query(Scan)
        .filter(
            Scan.client_id == client.id,
            Scan.status == "completed",
            Scan.completed_at < latest_scan.completed_at,
        )
        .order_by(desc(Scan.completed_at))
        .first()
    )
    prev_gs: GeoScore | None = (
        db.query(GeoScore).filter(GeoScore.scan_id == prev_scan.id).first()
        if prev_scan else None
    )

    client_results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
        )
        .all()
    )
    seen_count = sum(1 for r in client_results if r.brand_detected)
    total_count = len(client_results)

    competitors_orm = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    competitor_summaries: list[CompetitorSummary] = []
    for comp in competitors_orm:
        comp_results = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == latest_scan.id,
                ScanQueryResult.competitor_id == comp.id,
            )
            .all()
        )
        if comp_results:
            detected = sum(1 for r in comp_results if r.brand_detected)
            citability = round((detected / len(comp_results)) * 100, 2)
            competitor_summaries.append(
                CompetitorSummary(
                    name=comp.name,
                    ai_citability=citability,
                    is_winning=citability > current_gs.ai_citability,
                )
            )

    toolkit = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client.id).first()
    score_band, score_color = get_score_band(current_gs.overall_score)
    trend = _compute_trend(
        current_gs.overall_score, prev_gs.overall_score if prev_gs else None
    )
    recommendation = get_digest_action(
        client, current_gs.ai_citability, prev_gs.ai_citability if prev_gs else None
    )

    now = datetime.utcnow()
    return ReportData(
        period_start=now - timedelta(days=30),
        period_end=now,
        period_label=now.strftime("%B %Y"),
        overall_score=current_gs.overall_score,
        score_band=score_band,
        score_color=score_color,
        ai_citability=current_gs.ai_citability,
        brand_authority=current_gs.brand_authority,
        content_quality=current_gs.content_quality,
        technical_foundations=current_gs.technical_foundations,
        structured_data=current_gs.structured_data,
        prev_overall_score=prev_gs.overall_score if prev_gs else None,
        trend=trend,
        seen_count=seen_count,
        total_count=total_count,
        llms_verified=toolkit.llms_verified if toolkit else False,
        schema_verified=toolkit.schema_verified if toolkit else False,
        robots_verified=toolkit.robots_verified if toolkit else False,
        competitors=competitor_summaries,
        recommendation=recommendation,
    )


def _build_report_html(client: Client, data: ReportData) -> str:
    _, ai_color = get_score_band(data.ai_citability)
    _, ba_color = get_score_band(data.brand_authority)
    _, cq_color = get_score_band(data.content_quality)
    _, tf_color = get_score_band(data.technical_foundations)
    _, sd_color = get_score_band(data.structured_data)

    trend_messages = {
        "up":    f"&#8593; Score improved from {data.prev_overall_score:.0f} to {data.overall_score:.0f}",
        "down":  f"&#8595; Score decreased from {data.prev_overall_score:.0f} to {data.overall_score:.0f}",
        "flat":  f"&#8594; Score held steady at {data.overall_score:.0f}",
        "first": "First AI Visibility Report",
    }
    trend_colors = {"up": "#16a34a", "down": "#dc2626", "flat": "#6b7280", "first": "#6b7280"}
    trend_msg = trend_messages[data.trend]
    trend_color = trend_colors[data.trend]

    if data.competitors:
        comp_rows = "".join(
            f"""<tr>
              <td>{c.name}</td>
              <td class="{_score_css(get_score_band(c.ai_citability)[1])}">{c.ai_citability:.0f}%</td>
              <td>{"<span class='badge-red'>Winning</span>" if c.is_winning else "<span class='badge-green'>You are ahead</span>"}</td>
            </tr>"""
            for c in data.competitors
        )
    else:
        comp_rows = '<tr><td colspan="3" style="color:#9ca3af;">No competitors tracked yet.</td></tr>'

    generated_date = datetime.utcnow().strftime("%d %B %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>{_CSS}</style>
</head>
<body>

  <div class="cover page-break">
    <div class="logo">SeenBy</div>
    <div style="font-size:11pt;color:#64748b;margin-top:4px;">AI Visibility Intelligence</div>
    <div class="cover-client">{client.name}</div>
    <div class="cover-period">AI Visibility Report &middot; {data.period_label}</div>
    <div style="margin-top:56px;">
      <div class="score-box">
        <div class="score-box-value">{data.overall_score:.0f}</div>
        <div class="score-box-label">GEO Score &middot; {data.score_band.title()}</div>
      </div>
    </div>
    <div class="cover-footer">
      Report generated {generated_date}<br>
      Tracked by SeenBy &middot; contact@seenby.my
    </div>
  </div>

  <h2>AI Visibility Score</h2>
  <p style="font-size:12pt;font-weight:600;color:{trend_color};margin-bottom:16px;">{trend_msg}</p>
  <div class="stat-box">
    <div class="stat-label">Overall GEO Score</div>
    <div class="stat-value">{data.overall_score:.0f} <span style="font-size:14pt;color:#64748b;">/ 100</span></div>
    <div class="stat-sub">{data.score_band.title()} band</div>
  </div>

  <h2>Score Breakdown</h2>
  <table>
    <thead>
      <tr><th>Dimension</th><th>Score</th><th>Weight</th><th>Contribution</th><th>Source</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>AI Citability</td>
        <td class="{_score_css(ai_color)}">{data.ai_citability:.0f}</td>
        <td>40%</td><td>{data.ai_citability * 0.40:.1f}</td>
        <td>Automatic &mdash; Scan engine</td>
      </tr>
      <tr>
        <td>Brand Authority</td>
        <td class="{_score_css(ba_color)}">{data.brand_authority:.0f}</td>
        <td>20%</td><td>{data.brand_authority * 0.20:.1f}</td>
        <td>Assessed by SeenBy team<div class="manual-note">Manual assessment</div></td>
      </tr>
      <tr>
        <td>Content Quality</td>
        <td class="{_score_css(cq_color)}">{data.content_quality:.0f}</td>
        <td>20%</td><td>{data.content_quality * 0.20:.1f}</td>
        <td>Assessed by SeenBy team<div class="manual-note">Manual assessment</div></td>
      </tr>
      <tr>
        <td>Technical Foundations</td>
        <td class="{_score_css(tf_color)}">{data.technical_foundations:.0f}</td>
        <td>10%</td><td>{data.technical_foundations * 0.10:.1f}</td>
        <td>Automatic &mdash; Toolkit verified</td>
      </tr>
      <tr>
        <td>Structured Data</td>
        <td class="{_score_css(sd_color)}">{data.structured_data:.0f}</td>
        <td>10%</td><td>{data.structured_data * 0.10:.1f}</td>
        <td>Automatic &mdash; Toolkit verified</td>
      </tr>
    </tbody>
  </table>

  <h2>AI Visibility Frequency</h2>
  <div class="stat-box">
    <div class="stat-label">Seen by AI</div>
    <div class="stat-value">{data.seen_count}/{data.total_count}</div>
    <div class="stat-sub">
      {client.name} was seen by AI in {data.seen_count} out of {data.total_count} queries this period.
    </div>
  </div>

  <h2>Competitor Comparison</h2>
  <table>
    <thead><tr><th>Name</th><th>AI Citability</th><th>Status</th></tr></thead>
    <tbody>
      <tr>
        <td><strong>{client.name} (You)</strong></td>
        <td class="{_score_css(ai_color)}">{data.ai_citability:.0f}%</td>
        <td>&mdash;</td>
      </tr>
      {comp_rows}
    </tbody>
  </table>

  <h2>AI Readiness Toolkit</h2>
  <table>
    <thead><tr><th>File</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>llms.txt</td><td>{_verified_badge(data.llms_verified)}</td></tr>
      <tr><td>schema.json (JSON-LD)</td><td>{_verified_badge(data.schema_verified)}</td></tr>
      <tr><td>robots.txt (AI Bots)</td><td>{_verified_badge(data.robots_verified)}</td></tr>
    </tbody>
  </table>

  <h2>Recommended Action</h2>
  <div class="rec-box">
    <p style="margin:0;font-size:11pt;color:#0c4a6e;">{data.recommendation}</p>
  </div>

  <p style="margin-top:40px;font-size:9pt;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:12px;">
    This report was generated automatically by SeenBy. Manual dimension scores (Brand Authority,
    Content Quality) are assessed by the SeenBy team. Contact: contact@seenby.my
  </p>

</body>
</html>"""
```

- [ ] **Step 4: Run tests — expect pass**

```bash
poetry run pytest tests/test_report_service.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_report_service.py
git commit -m "feat: add report service data gathering and HTML template"
```

---

## Task 8: Report Service — Generate PDF + Send Email (TDD)

**Files:**
- Modify: `backend/app/services/report_service.py` (add `generate_report_pdf` + `send_report_email` + `_build_report_email_html`)
- Modify: `backend/tests/test_report_service.py` (append new tests)

- [ ] **Step 1: Write failing tests — append to test_report_service.py**

Append these tests to `backend/tests/test_report_service.py`:

```python
# ── generate_report_pdf ───────────────────────────────────────────────────────

def test_generate_report_pdf_returns_none_for_archived_client():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.archived_at = datetime.utcnow()
    db.get.return_value = client
    assert generate_report_pdf(uuid.uuid4(), db) is None


def test_generate_report_pdf_returns_none_when_no_scan_data():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.archived_at = None
    db.get.return_value = client
    with patch("app.services.report_service._gather_report_data", return_value=None):
        assert generate_report_pdf(uuid.uuid4(), db) is None


def test_generate_report_pdf_uploads_to_r2_and_returns_report():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = "Acme Corp"
    client.archived_at = None
    db.get.return_value = client

    with patch("app.services.report_service._gather_report_data", return_value=_make_report_data()), \
         patch("app.services.report_service.weasyprint") as mock_wp, \
         patch("app.services.report_service.upload_pdf", return_value="https://pub.seenby.my/reports/test.pdf") as mock_upload:
        mock_wp.HTML.return_value.write_pdf.return_value = b"fake-pdf-bytes"
        result = generate_report_pdf(client.id, db)

    mock_upload.assert_called_once()
    assert mock_upload.call_args[0][1] == b"fake-pdf-bytes"
    db.add.assert_called()
    db.commit.assert_called()


def test_generate_report_pdf_logs_report_generated_activity():
    from app.services.report_service import generate_report_pdf
    from app.models.activity_log import ActivityLog
    db = MagicMock()
    client = MagicMock()
    client.id = uuid.uuid4()
    client.archived_at = None
    db.get.return_value = client

    added_objects = []
    db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.report_service._gather_report_data", return_value=_make_report_data()), \
         patch("app.services.report_service.weasyprint") as mock_wp, \
         patch("app.services.report_service.upload_pdf", return_value="https://pub.seenby.my/r.pdf"):
        mock_wp.HTML.return_value.write_pdf.return_value = b"pdf"
        generate_report_pdf(client.id, db)

    event_types = [o.event_type for o in added_objects if hasattr(o, "event_type")]
    assert "report_generated" in event_types


# ── send_report_email ─────────────────────────────────────────────────────────

def _make_mock_report(sent_at=None):
    r = MagicMock()
    r.id = uuid.uuid4()
    r.client_id = uuid.uuid4()
    r.r2_key = "reports/client/20260601.pdf"
    r.r2_url = "https://pub.seenby.my/reports/client/20260601.pdf"
    r.period_start = datetime(2026, 5, 1)
    r.overall_score = 72.0
    r.sent_at = sent_at
    return r


def test_send_report_email_returns_false_when_already_sent():
    from app.services.report_service import send_report_email
    db = MagicMock()
    db.get.return_value = _make_mock_report(sent_at=datetime.utcnow())
    assert send_report_email(uuid.uuid4(), db) is False


def test_send_report_email_returns_false_when_no_contact_email():
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.contact_email = None
    db.get.side_effect = [report, client]
    assert send_report_email(uuid.uuid4(), db) is False


def test_send_report_email_sends_email_with_pdf_attachment():
    import resend as resend_module
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.name = "Acme Corp"
    client.contact_email = "client@acme.com"
    db.get.side_effect = [report, client]

    with patch("app.services.report_service.download_pdf", return_value=b"pdf-bytes"), \
         patch.object(resend_module.Emails, "send") as mock_send:
        result = send_report_email(uuid.uuid4(), db)

    assert result is True
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["client@acme.com"]
    assert "May 2026" in call_kwargs["subject"]
    assert len(call_kwargs["attachments"]) == 1
    assert call_kwargs["attachments"][0]["filename"].endswith(".pdf")


def test_send_report_email_marks_report_sent_and_logs_activity():
    import resend as resend_module
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.name = "Acme Corp"
    client.contact_email = "client@acme.com"
    db.get.side_effect = [report, client]

    added_objects = []
    db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.report_service.download_pdf", return_value=b"pdf-bytes"), \
         patch.object(resend_module.Emails, "send"):
        send_report_email(uuid.uuid4(), db)

    assert report.sent_at is not None
    event_types = [o.event_type for o in added_objects if hasattr(o, "event_type")]
    assert "report_sent" in event_types
    db.commit.assert_called()
```

- [ ] **Step 2: Run new tests — expect failure**

```bash
poetry run pytest tests/test_report_service.py -v -k "generate_report_pdf or send_report_email"
```

Expected: `ImportError: cannot import name 'generate_report_pdf'`

- [ ] **Step 3: Add generate_report_pdf + send_report_email + _build_report_email_html to report_service.py**

Append these three functions to the end of `backend/app/services/report_service.py`:

```python
import weasyprint
import resend as resend_module
from app.core.config import settings


def generate_report_pdf(client_id: uuid.UUID, db: Session) -> Report | None:
    """Generate PDF, upload to R2, save record. Returns None if client archived or no scan data."""
    client = db.get(Client, client_id)
    if not client or client.archived_at is not None:
        return None

    data = _gather_report_data(client, db)
    if data is None:
        logger.warning("no_scan_data_for_report", client_id=str(client_id))
        return None

    html = _build_report_html(client, data)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    key = f"reports/{client_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    r2_url = upload_pdf(key, pdf_bytes)

    report = Report(
        client_id=client_id,
        r2_key=key,
        r2_url=r2_url,
        period_start=data.period_start,
        period_end=data.period_end,
        overall_score=data.overall_score,
    )
    db.add(report)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="report_generated",
        note=f"Monthly report generated for {data.period_label}.",
    ))
    db.commit()
    db.refresh(report)
    logger.info("report_generated", client_id=str(client_id), report_id=str(report.id))
    return report


def send_report_email(report_id: uuid.UUID, db: Session) -> bool:
    """Download PDF from R2, email to client with attachment, mark sent. Returns False if already sent."""
    report = db.get(Report, report_id)
    if not report or report.sent_at is not None:
        return False

    client = db.get(Client, report.client_id)
    if not client or not client.contact_email:
        return False

    pdf_bytes = download_pdf(report.r2_key)
    period_label = report.period_start.strftime("%B %Y")
    filename = f"SeenBy-Report-{period_label.replace(' ', '-')}.pdf"

    resend_module.api_key = settings.RESEND_API_KEY
    resend_module.Emails.send({
        "from": "contact@seenby.my",
        "to": [client.contact_email],
        "subject": f"Your Monthly AI Visibility Report — {period_label} | {client.name}",
        "html": _build_report_email_html(client, report, period_label),
        "attachments": [{"filename": filename, "content": list(pdf_bytes)}],
    })

    report.sent_at = datetime.utcnow()
    db.add(ActivityLog(
        client_id=report.client_id,
        event_type="report_sent",
        note=f"Monthly report sent to {client.contact_email} for {period_label}.",
    ))
    db.commit()
    logger.info("report_sent", report_id=str(report_id), to=client.contact_email)
    return True


def _build_report_email_html(client: Client, report: Report, period_label: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#0f172a;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">SeenBy</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">Monthly AI Visibility Report</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">
            {client.name} &mdash; {period_label} Report
          </h2>
          <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">
            Your monthly AI Visibility Report is attached as a PDF. Open it to review
            your score breakdown, competitor comparison, and recommended actions.
          </p>
          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:24px;">
            <p style="margin:0 0 4px;font-size:13px;color:#6b7280;
                      text-transform:uppercase;letter-spacing:0.05em;">Overall GEO Score</p>
            <p style="margin:0;font-size:28px;font-weight:700;color:#0f172a;">
              {report.overall_score:.0f} / 100
            </p>
            <p style="margin:4px 0 0;font-size:14px;color:#6b7280;">
              Your AI Visibility Score for {period_label}.
            </p>
          </div>
          <p style="margin:32px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            Tracked by SeenBy &middot;
            <a href="mailto:contact@seenby.my"
               style="color:#9ca3af;text-decoration:none;">contact@seenby.my</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
```

Note: the `import weasyprint` and `import resend as resend_module` must be at the **top** of `report_service.py`, not inside the function. Move them to the top-level imports. The function body shows them here for clarity only.

- [ ] **Step 4: Run all report service tests — expect pass**

```bash
poetry run pytest tests/test_report_service.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_report_service.py
git commit -m "feat: add generate_report_pdf and send_report_email to report service"
```

---

## Task 9: Report API Routes + Register Router

**Files:**
- Create: `backend/app/api/v1/reports.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: Create reports.py**

Create `backend/app/api/v1/reports.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.report import Report
from app.schemas.report import ReportResponse

router = APIRouter(prefix="/clients/{client_id}/reports", tags=["reports"])


@router.post(
    "/generate",
    response_model=ReportResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_report(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    from workers.tasks.report_tasks import generate_client_report
    task = generate_client_report.delay(str(client_id))
    return {"task_id": task.id, "client_id": str(client_id), "status": "queued"}


@router.get(
    "",
    response_model=list[ReportResponse],
    dependencies=[Depends(require_api_key)],
)
def list_reports(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(Report)
        .filter(Report.client_id == client_id)
        .order_by(desc(Report.generated_at))
        .all()
    )


@router.post(
    "/{report_id}/send",
    dependencies=[Depends(require_api_key)],
)
def send_report(
    client_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if not report or report.client_id != client_id:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.sent_at is not None:
        raise HTTPException(status_code=409, detail="Report already sent")
    from app.services.report_service import send_report_email
    sent = send_report_email(report_id, db)
    return {"sent": sent, "report_id": str(report_id)}
```

Note: the `generate` endpoint returns a task ID (queued Celery job) rather than the Report directly, since PDF generation can take several seconds. The frontend polls or refreshes to see the new report appear.

- [ ] **Step 2: Update router.py to include reports**

In `backend/app/api/v1/router.py`, add `reports` to the import and include the router:

```python
from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors, toolkit, activity, digest, reports

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
router.include_router(toolkit.router)
router.include_router(activity.router)
router.include_router(digest.router)
router.include_router(reports.router)
```

- [ ] **Step 3: Verify routes are registered**

```bash
cd backend
poetry run python -c "from app.main import app; [print(r.path) for r in app.routes if 'report' in r.path]"
```

Expected output includes:
```
/api/v1/clients/{client_id}/reports/generate
/api/v1/clients/{client_id}/reports
/api/v1/clients/{client_id}/reports/{report_id}/send
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/reports.py backend/app/api/v1/router.py
git commit -m "feat: add report API routes (generate, list, send)"
```

---

## Task 10: Report Celery Tasks + Beat Schedule

**Files:**
- Create: `backend/workers/tasks/report_tasks.py`
- Modify: `backend/workers/celery_app.py`

- [ ] **Step 1: Create report_tasks.py**

Create `backend/workers/tasks/report_tasks.py`:

```python
import uuid
import structlog
from datetime import datetime, timedelta
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.report import Report
from app.services.report_service import generate_report_pdf

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.report_tasks.generate_client_report")
def generate_client_report(client_id: str) -> dict:
    """Manual trigger — generate PDF report for one client."""
    logger.info("generate_client_report_started", client_id=client_id)
    db = SessionLocal()
    try:
        report = generate_report_pdf(uuid.UUID(client_id), db)
        return {"generated": report is not None, "client_id": client_id}
    finally:
        db.close()


@celery_app.task(name="workers.tasks.report_tasks.check_and_generate_due_reports")
def check_and_generate_due_reports() -> dict:
    """Celery Beat task — runs daily at 9am UTC. Generates reports for clients due today."""
    logger.info("check_and_generate_due_reports_started")
    db = SessionLocal()
    generated = 0
    skipped = 0
    try:
        clients = (
            db.query(Client)
            .filter(
                Client.archived_at.is_(None),
                Client.contact_email.isnot(None),
            )
            .all()
        )
        for client in clients:
            if not _is_report_due(client, db):
                skipped += 1
                continue
            try:
                report = generate_report_pdf(client.id, db)
                if report:
                    generated += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(
                    "report_generation_failed",
                    client_id=str(client.id),
                    error=str(exc),
                )
                skipped += 1
        logger.info("check_and_generate_due_reports_done", generated=generated, skipped=skipped)
        return {"generated": generated, "skipped": skipped}
    finally:
        db.close()


def _is_report_due(client: Client, db: Session) -> bool:
    """Return True if 30 days have passed since signup (or last report)."""
    from sqlalchemy.orm import Session as _Session
    last_report: Report | None = (
        db.query(Report)
        .filter(Report.client_id == client.id)
        .order_by(Report.generated_at.desc())
        .first()
    )
    reference = last_report.generated_at if last_report else client.created_at
    return datetime.utcnow() >= reference + timedelta(days=30)
```

Note: `Session` is already imported at the top of the module via `from sqlalchemy.orm import Session` — add that import.

The correct top-level imports for `report_tasks.py`:
```python
import uuid
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.models.report import Report
from app.services.report_service import generate_report_pdf

logger = structlog.get_logger()
```

- [ ] **Step 2: Update celery_app.py — include report_tasks + add Beat schedule**

In `backend/workers/celery_app.py`, update `include` to add `workers.tasks.report_tasks` and add the Beat schedule entry:

```python
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "seenby",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.tasks.scan_tasks",
        "workers.tasks.digest_tasks",
        "workers.tasks.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "weekly-digest-monday-9am-utc": {
            "task": "workers.tasks.digest_tasks.send_all_weekly_digests",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
        },
        "daily-report-check-9am-utc": {
            "task": "workers.tasks.report_tasks.check_and_generate_due_reports",
            "schedule": crontab(hour=9, minute=0),
        },
    },
)
```

- [ ] **Step 3: Verify Celery can discover tasks**

```bash
cd backend
poetry run celery -A workers.celery_app inspect registered 2>/dev/null | grep report
```

Expected to see `workers.tasks.report_tasks.generate_client_report` and `workers.tasks.report_tasks.check_and_generate_due_reports`.

- [ ] **Step 4: Commit**

```bash
git add backend/workers/tasks/report_tasks.py backend/workers/celery_app.py
git commit -m "feat: add report Celery tasks and daily Beat schedule"
```

---

## Task 11: Frontend Types + API Functions

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add Report interface to types/index.ts**

Append to the end of `frontend/src/types/index.ts`:

```typescript
export interface Report {
  id: string
  client_id: string
  r2_url: string
  period_start: string
  period_end: string
  overall_score: number
  generated_at: string
  sent_at: string | null
}
```

- [ ] **Step 2: Add report imports to api.ts**

In `frontend/src/lib/api.ts`, add `Report` to the import line at the top:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry, Report } from "@/types"
```

- [ ] **Step 3: Add report API functions to api.ts**

Append to the end of `frontend/src/lib/api.ts`:

```typescript
// ── Reports ───────────────────────────────────────────────────────────────────

export function getReports(clientId: string): Promise<Report[]> {
  return apiFetch<Report[]>(`/api/v1/clients/${clientId}/reports`)
}

export function generateReport(clientId: string): Promise<{ task_id: string; client_id: string; status: string }> {
  return apiFetch<{ task_id: string; client_id: string; status: string }>(
    `/api/v1/clients/${clientId}/reports/generate`,
    { method: "POST" },
  )
}

export function sendReport(clientId: string, reportId: string): Promise<{ sent: boolean; report_id: string }> {
  return apiFetch<{ sent: boolean; report_id: string }>(
    `/api/v1/clients/${clientId}/reports/${reportId}/send`,
    { method: "POST" },
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add Report type and report API functions to frontend"
```

---

## Task 12: Reports Frontend Page + Activity Log Labels

**Files:**
- Create: `frontend/src/app/clients/[id]/reports/ReportsClient.tsx`
- Create: `frontend/src/app/clients/[id]/reports/actions.ts`
- Modify: `frontend/src/app/clients/[id]/reports/page.tsx`
- Modify: `frontend/src/app/clients/[id]/activity/page.tsx`

- [ ] **Step 1: Create actions.ts**

Create `frontend/src/app/clients/[id]/reports/actions.ts`:

```typescript
"use server"

import { generateReport, sendReport } from "@/lib/api"
import { revalidatePath } from "next/cache"

export async function triggerGenerateReport(clientId: string) {
  await generateReport(clientId)
  revalidatePath(`/clients/${clientId}/reports`)
}

export async function triggerSendReport(clientId: string, reportId: string) {
  await sendReport(clientId, reportId)
  revalidatePath(`/clients/${clientId}/reports`)
}
```

- [ ] **Step 2: Create ReportsClient.tsx**

Create `frontend/src/app/clients/[id]/reports/ReportsClient.tsx`:

```typescript
"use client"

import { useState, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { FileText, Download, Send, Loader2 } from "lucide-react"
import type { Report } from "@/types"
import { triggerGenerateReport, triggerSendReport } from "./actions"

interface Props {
  clientId: string
  initialReports: Report[]
}

function formatPeriod(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-MY", {
    month: "long",
    year: "numeric",
  })
}

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

function ScoreBadge({ score }: { score: number }) {
  const s = Math.floor(score)
  const variant =
    s >= 65 ? "default" : s >= 50 ? "secondary" : "destructive"
  return <Badge variant={variant}>{score.toFixed(0)}</Badge>
}

export function ReportsClient({ clientId, initialReports }: Props) {
  const [reports, setReports] = useState<Report[]>(initialReports)
  const [isPending, startTransition] = useTransition()
  const [sendingId, setSendingId] = useState<string | null>(null)

  function handleGenerate() {
    startTransition(async () => {
      await triggerGenerateReport(clientId)
      // Page revalidation will refresh the data on next render
    })
  }

  function handleSend(reportId: string) {
    setSendingId(reportId)
    startTransition(async () => {
      await triggerSendReport(clientId, reportId)
      setSendingId(null)
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Monthly Reports</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Generated automatically 30 days after signup, then every 30 days.
            Review before sending.
          </p>
        </div>
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <FileText className="h-4 w-4 mr-2" />
          )}
          Generate Report
        </Button>
      </div>

      {reports.length === 0 ? (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-3 opacity-40" />
          <p className="font-medium">No reports yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Generate Report&rdquo; to create the first monthly report.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Period</TableHead>
              <TableHead>GEO Score</TableHead>
              <TableHead>Generated</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {reports.map((report) => (
              <TableRow key={report.id}>
                <TableCell className="font-medium">
                  {formatPeriod(report.period_start)}
                </TableCell>
                <TableCell>
                  <ScoreBadge score={report.overall_score} />
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {formatDate(report.generated_at)}
                </TableCell>
                <TableCell>
                  {report.sent_at ? (
                    <Badge variant="outline" className="text-green-600 border-green-200">
                      Sent {formatDate(report.sent_at)}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-amber-600 border-amber-200">
                      Not yet sent
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <Button variant="ghost" size="sm" asChild>
                      <a href={report.r2_url} target="_blank" rel="noopener noreferrer">
                        <Download className="h-4 w-4 mr-1" />
                        Download
                      </a>
                    </Button>
                    {!report.sent_at && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleSend(report.id)}
                        disabled={sendingId === report.id || isPending}
                      >
                        {sendingId === report.id ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : (
                          <Send className="h-4 w-4 mr-1" />
                        )}
                        Send to Client
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Update reports/page.tsx**

Replace the entire contents of `frontend/src/app/clients/[id]/reports/page.tsx`:

```typescript
import { getReports } from "@/lib/api"
import { ReportsClient } from "./ReportsClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ReportsPage({ params }: Props) {
  const { id } = await params
  let reports = []
  try {
    reports = await getReports(id)
  } catch {
    // backend down — show empty state
  }
  return <ReportsClient clientId={id} initialReports={reports} />
}
```

- [ ] **Step 4: Add report event types to activity/page.tsx**

In `frontend/src/app/clients/[id]/activity/page.tsx`:

1. Add `FileText` to the lucide-react import:
```typescript
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail, FileText } from "lucide-react"
```

2. Add to `EVENT_LABELS`:
```typescript
const EVENT_LABELS: Record<string, string> = {
  scan_completed: "Scan completed",
  scan_failed: "Scan failed",
  toolkit_generated: "Toolkit generated",
  toolkit_verified: "Toolkit files verified",
  client_created: "Client onboarded",
  digest_sent: "Weekly digest sent",
  report_generated: "Monthly report generated",
  report_sent: "Monthly report sent",
}
```

3. Add cases to `EventIcon`:
```typescript
case "report_generated":
  return <FileText className={`${cls} text-sky-500`} />
case "report_sent":
  return <FileText className={`${cls} text-green-500`} />
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/clients/[id]/reports/ frontend/src/app/clients/[id]/activity/page.tsx
git commit -m "feat: build Reports frontend page with generate and send-to-client actions"
```

---

## Self-Review Checklist

### Spec Coverage

| Requirement (CLAUDE.md §7, §8) | Task |
|---|---|
| Auto-generated via WeasyPrint | Task 8 — `generate_report_pdf` calls `weasyprint.HTML(...).write_pdf()` |
| Faris reviews before sending | Task 9 — generate queues to Celery, send is a separate manual POST |
| Sent 30 days after signup, then every 30 days | Task 10 — `_is_report_due` checks 30-day interval |
| Contact email: contact@seenby.my | Task 8 — `_build_report_email_html` uses `contact@seenby.my` |
| PDF stored in Cloudflare R2, never in Postgres as base64 | Task 5 (R2 service), Task 8 (upload before DB save) |
| Admin panel navigation /clients/[id]/reports | Task 12 (page.tsx) |
| Manual dimension scores show "Assessed by SeenBy team" | Task 7 — `_build_report_html` includes that label |
| Score band constants from constants.py (no hardcoding) | Task 7 — uses `get_score_band()` from `scoring_service` |
| Activity log event logged | Tasks 8, 10 — `report_generated` and `report_sent` events |
| Activity page labels for new events | Task 12 — adds labels + icons |

### Placeholder Scan: None found.

### Type Consistency

- `Report` ORM model → `ReportResponse` schema → `Report` TypeScript interface: all use `r2_url`, `period_start`, `period_end`, `overall_score`, `generated_at`, `sent_at` — consistent.
- `generate_report_pdf(client_id: uuid.UUID, db: Session) -> Report | None` — used in `report_tasks.py` with `generate_report_pdf(uuid.UUID(client_id), db)` — consistent.
- `send_report_email(report_id: uuid.UUID, db: Session) -> bool` — used in `reports.py` route — consistent.
- `upload_pdf(key: str, pdf_bytes: bytes) -> str` — used in `report_service.py` — consistent.
- `download_pdf(key: str) -> bytes` — used in `send_report_email` — consistent.
