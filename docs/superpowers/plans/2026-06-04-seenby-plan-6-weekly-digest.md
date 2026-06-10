# SeenBy Plan 6: Weekly Email Digest + Claude-Generated Actions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the weekly email digest — a Celery Beat task that runs every Monday and sends each client a visibility update email, with Claude Haiku generating a 1-sentence action when their AI Citability score changes ≥5pts vs the previous scan.

**Architecture:** Four new backend files handle concerns in strict layers: `email_service.py` (Resend API wrapper), `claude_action.py` (action generation or static-tip fallback), `digest_service.py` (data computation + HTML builder + orchestration), `digest_tasks.py` (Celery task + Beat schedule). A `POST /api/v1/digest/trigger/{client_id}` endpoint lets Faris manually trigger a single-client digest for testing. No DB migration required — all data comes from existing `scans`, `geo_scores`, `scan_query_results`, and `activity_log` tables.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Celery 5 + Beat · Resend Python SDK · Anthropic Python SDK (claude-haiku-4-5-20251001) · Poetry

---

## File Map

```
backend/
├── pyproject.toml                           MODIFY — add resend dependency
├── app/
│   ├── core/
│   │   ├── config.py                        MODIFY — add RESEND_API_KEY
│   │   └── constants.py                     MODIFY — add DIGEST_STATIC_TIPS
│   ├── services/
│   │   ├── email_service.py                 CREATE — Resend send_email wrapper
│   │   ├── claude_action.py                 CREATE — get_digest_action (Haiku or static tip)
│   │   └── digest_service.py                CREATE — send_client_digest, _compute_digest_data
│   └── api/v1/
│       ├── digest.py                        CREATE — POST /digest/trigger/{client_id}
│       └── router.py                        MODIFY — include digest router
├── workers/
│   ├── celery_app.py                        MODIFY — include digest_tasks, add beat_schedule
│   └── tasks/
│       └── digest_tasks.py                  CREATE — send_all_weekly_digests, send_single_client_digest
└── tests/
    ├── test_email_service.py                CREATE
    ├── test_claude_action.py                CREATE
    └── test_digest_service.py               CREATE

frontend/
└── src/app/clients/[id]/activity/page.tsx   MODIFY — add digest_sent to EVENT_LABELS + EventIcon
```

---

## Task 1: Dependency + Config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add resend to pyproject.toml**

Open `backend/pyproject.toml`. In `[tool.poetry.dependencies]`, add after the `anthropic` line:

```toml
resend = "^2.0"
```

- [ ] **Step 2: Install the dependency**

```bash
cd backend
poetry add resend
```

Expected: Poetry resolves and installs `resend 2.x` with no conflicts.

- [ ] **Step 3: Add RESEND_API_KEY to config.py**

Replace the full contents of `backend/app/core/config.py`:

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
    RESEND_API_KEY: str

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
```

- [ ] **Step 4: Add RESEND_API_KEY to .env**

Open `backend/.env`. Add:

```
RESEND_API_KEY=re_your_resend_api_key_here
```

Get the key from resend.com → API Keys.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/poetry.lock backend/app/core/config.py
git commit -m "feat: add resend dependency and RESEND_API_KEY config"
```

---

## Task 2: Constants Update

**Files:**
- Modify: `backend/app/core/constants.py`

- [ ] **Step 1: Append DIGEST_STATIC_TIPS to constants.py**

Open `backend/app/core/constants.py`. Append at the very end of the file:

```python
# One static tip per score band — shown when AI Citability change is < 5pts vs previous scan
DIGEST_STATIC_TIPS: Final = {
    "excellent": "Keep publishing content featuring your brand — consistent visibility cements AI recognition over time.",
    "good": "Consider adding a frequently asked questions page — AI models surface structured Q&A content readily.",
    "fair": "Claim your business on Google Business Profile and Apple Maps — AI models draw from structured directory data.",
    "developing": "Your llms.txt file describes your business to AI crawlers. Verify it is live and reflects your core services.",
    "low": "Add your brand name naturally throughout your website copy — AI models recognize brands through consistent contextual mentions.",
}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/constants.py
git commit -m "feat: add DIGEST_STATIC_TIPS constants"
```

---

## Task 3: Email Service (TDD)

**Files:**
- Create: `backend/tests/test_email_service.py`
- Create: `backend/app/services/email_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_email_service.py`:

```python
from unittest.mock import patch, MagicMock


def test_send_email_calls_resend_with_correct_params():
    mock_emails = MagicMock()
    with patch("app.services.email_service.resend") as mock_resend:
        mock_resend.Emails = mock_emails
        from app.services import email_service
        email_service.send_email(
            to="client@example.com",
            subject="Your update",
            html_body="<p>Hello</p>",
        )
    mock_emails.send.assert_called_once_with({
        "from": "contact@seenby.my",
        "to": ["client@example.com"],
        "subject": "Your update",
        "html": "<p>Hello</p>",
    })
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd backend
pytest tests/test_email_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.email_service'`

- [ ] **Step 3: Create email_service.py**

Create `backend/app/services/email_service.py`:

```python
import resend
from app.core.config import settings


def send_email(to: str, subject: str, html_body: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": "contact@seenby.my",
        "to": [to],
        "subject": subject,
        "html": html_body,
    })
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend
pytest tests/test_email_service.py -v
```

Expected:
```
test_send_email_calls_resend_with_correct_params PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_email_service.py backend/app/services/email_service.py
git commit -m "feat: add email service with Resend wrapper"
```

---

## Task 4: Claude Action Service (TDD)

**Files:**
- Create: `backend/tests/test_claude_action.py`
- Create: `backend/app/services/claude_action.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_claude_action.py`:

```python
from unittest.mock import patch, MagicMock


def _make_client(name="Test Brand", industry="Technology"):
    c = MagicMock()
    c.name = name
    c.industry = industry
    return c


def test_returns_static_tip_when_score_change_below_threshold():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    result = get_digest_action(
        client=client,
        current_ai_citability=62.0,
        prev_ai_citability=60.0,  # change = 2pts, below 5pt threshold
    )
    assert result == DIGEST_STATIC_TIPS["fair"]


def test_returns_static_tip_when_no_previous_score():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    result = get_digest_action(
        client=client,
        current_ai_citability=30.0,
        prev_ai_citability=None,
    )
    assert result == DIGEST_STATIC_TIPS["low"]


def test_calls_claude_when_score_increases_by_5_or_more():
    from app.services.claude_action import get_digest_action
    mock_content = MagicMock()
    mock_content.text = "Publish a blog post featuring your brand name."
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = get_digest_action(
            client=client,
            current_ai_citability=75.0,
            prev_ai_citability=60.0,  # change = 15pts, above threshold
        )
    assert result == "Publish a blog post featuring your brand name."
    mock_cls.return_value.messages.create.assert_called_once()


def test_calls_claude_when_score_drops_by_5_or_more():
    from app.services.claude_action import get_digest_action
    mock_content = MagicMock()
    mock_content.text = "Add your brand to three new business directories this week."
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = get_digest_action(
            client=client,
            current_ai_citability=55.0,
            prev_ai_citability=70.0,  # drop = 15pts, above threshold
        )
    assert result == "Add your brand to three new business directories this week."


def test_falls_back_to_static_tip_when_claude_raises():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("API error")
        result = get_digest_action(
            client=client,
            current_ai_citability=75.0,
            prev_ai_citability=60.0,  # 15pt change triggers Claude, but it raises
        )
    # 75 is in "good" band (65-79)
    assert result == DIGEST_STATIC_TIPS["good"]
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend
pytest tests/test_claude_action.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.claude_action'`

- [ ] **Step 3: Create claude_action.py**

Create `backend/app/services/claude_action.py`:

```python
import anthropic
from app.core.config import settings
from app.core.constants import SCORE_BANDS, DIGEST_STATIC_TIPS
from app.models.client import Client


def get_digest_action(
    client: Client,
    current_ai_citability: float,
    prev_ai_citability: float | None,
) -> str:
    score_change = (
        abs(current_ai_citability - prev_ai_citability)
        if prev_ai_citability is not None
        else 0.0
    )
    if score_change >= 5.0:
        try:
            return _generate_claude_action(client, current_ai_citability, prev_ai_citability)
        except Exception:
            pass
    return DIGEST_STATIC_TIPS[_score_band(current_ai_citability)]


def _score_band(score: float) -> str:
    for band, (lo, hi) in SCORE_BANDS.items():
        if lo <= score <= hi:
            return band
    return "low"


def _generate_claude_action(
    client: Client,
    current: float,
    prev: float | None,
) -> str:
    direction = "increased" if (prev is not None and current > prev) else "decreased"
    prompt = (
        f"You are a concise AI visibility advisor. "
        f"A business called '{client.name}' in the {client.industry} industry "
        f"had their AI visibility frequency {direction} "
        f"from {prev:.1f}% to {current:.1f}% this week. "
        f"Write exactly one sentence (under 20 words) recommending one specific action "
        f"they can take to improve or maintain their AI visibility. "
        f"Be direct. Do not use 'consider', 'you might', or 'perhaps'."
    )
    ai_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
```

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd backend
pytest tests/test_claude_action.py -v
```

Expected:
```
test_returns_static_tip_when_score_change_below_threshold PASSED
test_returns_static_tip_when_no_previous_score PASSED
test_calls_claude_when_score_increases_by_5_or_more PASSED
test_calls_claude_when_score_drops_by_5_or_more PASSED
test_falls_back_to_static_tip_when_claude_raises PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_claude_action.py backend/app/services/claude_action.py
git commit -m "feat: add Claude action service with static tip fallback"
```

---

## Task 5: Digest Service (TDD)

**Files:**
- Create: `backend/tests/test_digest_service.py`
- Create: `backend/app/services/digest_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_digest_service.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.digest_service import DigestData, _compute_trend, _detect_first_seen


# ── _compute_trend ────────────────────────────────────────────────────────────

def test_trend_up_when_current_exceeds_prev_by_more_than_half_point():
    assert _compute_trend(70.0, 60.0) == "up"


def test_trend_down_when_current_below_prev_by_more_than_half_point():
    assert _compute_trend(55.0, 70.0) == "down"


def test_trend_flat_when_change_is_within_half_point():
    assert _compute_trend(60.3, 60.0) == "flat"


def test_trend_first_when_no_previous_scan():
    assert _compute_trend(50.0, None) == "first"


# ── _detect_first_seen ────────────────────────────────────────────────────────

def test_first_seen_false_when_seen_count_is_zero():
    db = MagicMock()
    assert _detect_first_seen(seen_count=0, prev_scan=None, db=db) is False


def test_first_seen_true_when_seen_and_no_previous_scan():
    db = MagicMock()
    assert _detect_first_seen(seen_count=3, prev_scan=None, db=db) is True


def test_first_seen_true_when_prev_scan_had_zero_detections():
    prev_scan = MagicMock()
    prev_scan.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    assert _detect_first_seen(seen_count=2, prev_scan=prev_scan, db=db) is True


def test_first_seen_false_when_prev_scan_also_had_detections():
    prev_scan = MagicMock()
    prev_scan.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 5
    assert _detect_first_seen(seen_count=4, prev_scan=prev_scan, db=db) is False


# ── send_client_digest ────────────────────────────────────────────────────────

def _make_client(contact_email="client@example.com", archived=False):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = "Test Brand"
    c.industry = "Technology"
    c.contact_email = contact_email
    c.archived_at = datetime.utcnow() if archived else None
    return c


def _make_digest_data():
    return DigestData(
        seen_count=5,
        total_count=8,
        current_ai_citability=62.5,
        current_overall_score=60.0,
        prev_ai_citability=50.0,
        trend="up",
        is_first_seen=False,
        action_text="Publish a blog post featuring your brand name.",
    )


def test_send_client_digest_skips_archived_client():
    db = MagicMock()
    db.get.return_value = _make_client(archived=True)
    from app.services.digest_service import send_client_digest
    assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_skips_client_without_contact_email():
    db = MagicMock()
    db.get.return_value = _make_client(contact_email=None)
    from app.services.digest_service import send_client_digest
    assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_skips_when_no_scan_this_week():
    db = MagicMock()
    db.get.return_value = _make_client()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=None):
        assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_sends_email_and_returns_true():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    data = _make_digest_data()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email") as mock_send:
        result = send_client_digest(client.id, db)
    assert result is True
    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert kwargs["to"] == "client@example.com"
    assert "60" in kwargs["subject"]
    assert "Test Brand" in kwargs["subject"]


def test_send_client_digest_writes_digest_sent_activity_log_entry():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    data = _make_digest_data()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email"):
        send_client_digest(client.id, db)
    db.add.assert_called()
    db.commit.assert_called()
    added_obj = db.add.call_args[0][0]
    assert added_obj.event_type == "digest_sent"
    assert "client@example.com" in added_obj.note


def test_email_html_contains_seen_count_and_trend_message():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    data = _make_digest_data()  # trend="up", seen_count=5, total_count=8
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=capture):
        send_client_digest(client.id, db)
    html = captured["html_body"]
    assert "5/8" in html
    assert "improved" in html  # trend "up" → "Your AI visibility improved"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend
pytest tests/test_digest_service.py -v
```

Expected: `ImportError: cannot import name 'DigestData' from 'app.services.digest_service'`

- [ ] **Step 3: Create digest_service.py**

Create `backend/app/services/digest_service.py`:

```python
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
import structlog

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.services.email_service import send_email
from app.services.claude_action import get_digest_action

logger = structlog.get_logger()


@dataclass
class DigestData:
    seen_count: int
    total_count: int
    current_ai_citability: float
    current_overall_score: float
    prev_ai_citability: float | None
    trend: str  # "up" | "down" | "flat" | "first"
    is_first_seen: bool
    action_text: str


def send_client_digest(client_id: uuid.UUID, db: Session) -> bool:
    """Returns True if digest was sent, False if skipped."""
    client = db.get(Client, client_id)
    if not client or client.archived_at is not None or not client.contact_email:
        return False

    data = _compute_digest_data(client, db)
    if data is None:
        return False

    subject = (
        f"Your AI Visibility Update — {data.current_overall_score:.0f} GEO Score"
        f" | {client.name}"
    )
    html = _build_email_html(client, data)
    send_email(to=client.contact_email, subject=subject, html_body=html)

    db.add(ActivityLog(
        client_id=client_id,
        event_type="digest_sent",
        note=f"Weekly digest sent to {client.contact_email}.",
    ))
    db.commit()
    logger.info("digest_sent", client_id=str(client_id), to=client.contact_email)
    return True


def _compute_digest_data(client: Client, db: Session) -> DigestData | None:
    since = datetime.utcnow() - timedelta(days=7)

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
        db.query(GeoScore)
        .filter(GeoScore.scan_id == latest_scan.id)
        .first()
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
    prev_gs: GeoScore | None = None
    if prev_scan:
        prev_gs = (
            db.query(GeoScore)
            .filter(GeoScore.scan_id == prev_scan.id)
            .first()
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

    current_citability = current_gs.ai_citability
    prev_citability = prev_gs.ai_citability if prev_gs else None

    trend = _compute_trend(current_citability, prev_citability)
    is_first_seen = _detect_first_seen(seen_count, prev_scan, db)
    action_text = get_digest_action(client, current_citability, prev_citability)

    return DigestData(
        seen_count=seen_count,
        total_count=total_count,
        current_ai_citability=current_citability,
        current_overall_score=current_gs.overall_score,
        prev_ai_citability=prev_citability,
        trend=trend,
        is_first_seen=is_first_seen,
        action_text=action_text,
    )


def _compute_trend(current: float, prev: float | None) -> str:
    if prev is None:
        return "first"
    if current > prev + 0.5:
        return "up"
    if current < prev - 0.5:
        return "down"
    return "flat"


def _detect_first_seen(seen_count: int, prev_scan: Scan | None, db: Session) -> bool:
    if seen_count == 0:
        return False
    if prev_scan is None:
        return True
    prev_detected = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == prev_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.brand_detected.is_(True),
        )
        .count()
    )
    return prev_detected == 0


def _build_email_html(client: Client, data: DigestData) -> str:
    trend_messages = {
        "up":    "Your AI visibility improved this week ↑",
        "down":  "Your AI visibility decreased this week ↓",
        "flat":  "Your AI visibility held steady this week →",
        "first": "This is your first SeenBy weekly update.",
    }
    trend_colors = {
        "up":    "#16a34a",
        "down":  "#dc2626",
        "flat":  "#6b7280",
        "first": "#6b7280",
    }
    trend_msg = trend_messages[data.trend]
    trend_color = trend_colors[data.trend]

    milestone_block = ""
    if data.is_first_seen:
        milestone_block = f"""
        <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 16px;
                    margin-bottom:20px;border-radius:4px;">
          <strong style="color:#15803d;">First time Gemini saw your brand!</strong>
          <p style="margin:4px 0 0;color:#166534;font-size:14px;">
            AI models detected {client.name} in search results for the first time this week.
          </p>
        </div>"""

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
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">Weekly AI Visibility Update</p>
        </td></tr>

        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">
            {client.name} &mdash; Weekly Update
          </h2>
          <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">
            Here is how AI models saw your brand this week.
          </p>

          {milestone_block}

          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                      padding:20px;margin-bottom:20px;">
            <p style="margin:0 0 4px;font-size:13px;color:#6b7280;
                      text-transform:uppercase;letter-spacing:0.05em;">
              AI Visibility Frequency
            </p>
            <p style="margin:0;font-size:28px;font-weight:700;color:#0f172a;">
              {data.seen_count}/{data.total_count}
            </p>
            <p style="margin:4px 0 0;font-size:14px;color:#6b7280;">
              Seen by AI <strong>{data.seen_count} out of {data.total_count} times</strong> this week.
            </p>
          </div>

          <p style="color:{trend_color};font-size:15px;font-weight:600;margin:0 0 24px;">
            {trend_msg}
          </p>

          <div style="border-top:1px solid #e5e7eb;padding-top:20px;">
            <p style="margin:0 0 8px;font-size:13px;color:#6b7280;
                      text-transform:uppercase;letter-spacing:0.05em;">
              Action This Week
            </p>
            <p style="margin:0;font-size:15px;color:#0f172a;line-height:1.6;">
              {data.action_text}
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

- [ ] **Step 4: Run tests — expect all PASS**

```bash
cd backend
pytest tests/test_digest_service.py -v
```

Expected:
```
test_trend_up_when_current_exceeds_prev_by_more_than_half_point PASSED
test_trend_down_when_current_below_prev_by_more_than_half_point PASSED
test_trend_flat_when_change_is_within_half_point PASSED
test_trend_first_when_no_previous_scan PASSED
test_first_seen_false_when_seen_count_is_zero PASSED
test_first_seen_true_when_seen_and_no_previous_scan PASSED
test_first_seen_true_when_prev_scan_had_zero_detections PASSED
test_first_seen_false_when_prev_scan_also_had_detections PASSED
test_send_client_digest_skips_archived_client PASSED
test_send_client_digest_skips_client_without_contact_email PASSED
test_send_client_digest_skips_when_no_scan_this_week PASSED
test_send_client_digest_sends_email_and_returns_true PASSED
test_send_client_digest_writes_digest_sent_activity_log_entry PASSED
test_email_html_contains_seen_count_and_trend_message PASSED
```

- [ ] **Step 5: Run full test suite**

```bash
cd backend
pytest tests/ -v
```

Expected: all existing tests pass plus the 14 new digest service tests.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_digest_service.py backend/app/services/digest_service.py
git commit -m "feat: add digest service with email builder and trend detection"
```

---

## Task 6: Celery Task + Beat Schedule

**Files:**
- Create: `backend/workers/tasks/digest_tasks.py`
- Modify: `backend/workers/celery_app.py`

- [ ] **Step 1: Create digest_tasks.py**

Create `backend/workers/tasks/digest_tasks.py`:

```python
# backend/workers/tasks/digest_tasks.py
import uuid
import structlog
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.client import Client
from app.services.digest_service import send_client_digest

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.digest_tasks.send_all_weekly_digests")
def send_all_weekly_digests() -> dict:
    """Celery Beat task — runs every Monday 9am UTC."""
    logger.info("send_all_weekly_digests_started")
    db = SessionLocal()
    try:
        clients = (
            db.query(Client)
            .filter(
                Client.archived_at.is_(None),
                Client.contact_email.isnot(None),
            )
            .all()
        )
        sent = 0
        skipped = 0
        for client in clients:
            try:
                if send_client_digest(client.id, db):
                    sent += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.error(
                    "digest_failed_for_client",
                    client_id=str(client.id),
                    error=str(exc),
                )
                skipped += 1
        logger.info("send_all_weekly_digests_done", sent=sent, skipped=skipped)
        return {"sent": sent, "skipped": skipped}
    finally:
        db.close()


@celery_app.task(name="workers.tasks.digest_tasks.send_single_client_digest")
def send_single_client_digest(client_id: str) -> dict:
    """Manual trigger task for one client — dispatched by the admin trigger endpoint."""
    logger.info("send_single_client_digest_started", client_id=client_id)
    db = SessionLocal()
    try:
        was_sent = send_client_digest(uuid.UUID(client_id), db)
        return {"sent": was_sent, "client_id": client_id}
    finally:
        db.close()
```

- [ ] **Step 2: Update celery_app.py with digest_tasks and Beat schedule**

Replace the full contents of `backend/workers/celery_app.py`:

```python
# backend/workers/celery_app.py
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "seenby",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["workers.tasks.scan_tasks", "workers.tasks.digest_tasks"],
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
    },
)
```

- [ ] **Step 3: Run full test suite — no regressions**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/workers/tasks/digest_tasks.py backend/workers/celery_app.py
git commit -m "feat: add weekly digest Celery task with Monday 9am Beat schedule"
```

---

## Task 7: Manual Trigger Endpoint

**Files:**
- Create: `backend/app/api/v1/digest.py`
- Modify: `backend/app/api/v1/router.py`

- [ ] **Step 1: Create the trigger endpoint**

Create `backend/app/api/v1/digest.py`:

```python
import uuid
from fastapi import APIRouter, Depends
from app.core.auth import require_api_key

router = APIRouter(prefix="/digest", tags=["digest"])


@router.post(
    "/trigger/{client_id}",
    dependencies=[Depends(require_api_key)],
)
def trigger_digest(client_id: uuid.UUID) -> dict:
    from workers.tasks.digest_tasks import send_single_client_digest
    task = send_single_client_digest.delay(str(client_id))
    return {"task_id": task.id, "client_id": str(client_id)}
```

- [ ] **Step 2: Register the router**

Replace the full contents of `backend/app/api/v1/router.py`:

```python
from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors, toolkit, activity, digest

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
router.include_router(toolkit.router)
router.include_router(activity.router)
router.include_router(digest.router)
```

- [ ] **Step 3: Run full test suite**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/digest.py backend/app/api/v1/router.py
git commit -m "feat: add digest manual trigger endpoint POST /api/v1/digest/trigger/{client_id}"
```

---

## Task 8: Frontend — Activity Log Update

**Files:**
- Modify: `frontend/src/app/clients/[id]/activity/page.tsx`

- [ ] **Step 1: Add Mail to lucide-react import**

Open `frontend/src/app/clients/[id]/activity/page.tsx`. Find the import line:

```typescript
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus } from "lucide-react"
```

Replace with:

```typescript
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail } from "lucide-react"
```

- [ ] **Step 2: Add digest_sent to EVENT_LABELS**

Find the `EVENT_LABELS` object:

```typescript
const EVENT_LABELS: Record<string, string> = {
  scan_completed: "Scan completed",
  scan_failed: "Scan failed",
  toolkit_generated: "Toolkit generated",
  toolkit_verified: "Toolkit files verified",
  client_created: "Client onboarded",
}
```

Replace with:

```typescript
const EVENT_LABELS: Record<string, string> = {
  scan_completed: "Scan completed",
  scan_failed: "Scan failed",
  toolkit_generated: "Toolkit generated",
  toolkit_verified: "Toolkit files verified",
  client_created: "Client onboarded",
  digest_sent: "Weekly digest sent",
}
```

- [ ] **Step 3: Add digest_sent case to EventIcon**

Find the `EventIcon` function. Add a case before `default:`:

```typescript
    case "digest_sent":
      return <Mail className={`${cls} text-indigo-500`} />
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/clients/[id]/activity/page.tsx"
git commit -m "feat: add digest_sent event label and icon to activity log UI"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Celery Beat runs every Monday | Task 6 (`crontab(hour=9, minute=0, day_of_week=1)`) |
| No scan that week → no email | Task 5 (`_compute_digest_data` returns None when no scan in 7 days) |
| Current AI Citability score | Task 5 (`current_ai_citability` + `seen_count/total_count` in HTML) |
| Trend vs previous scan | Task 5 (`_compute_trend`, trend message in email HTML) |
| "Seen by Gemini X out of 8 times" | Task 5 (`seen_count/total_count` from client-only queries) |
| Milestone "First time Gemini saw your brand" | Task 5 (`_detect_first_seen`, `milestone_block` in HTML) |
| Claude Haiku action when ±5pt score change | Task 4 (`get_digest_action` with `score_change >= 5`) |
| Static tip otherwise | Task 4 (`DIGEST_STATIC_TIPS` fallback) |
| Claude API failure → falls back to static tip | Task 4 (try/except in `get_digest_action`) |
| Sent to client's `contact_email` | Task 5 (`send_email(to=client.contact_email, ...)`) |
| Sender `contact@seenby.my` | Task 3 (hardcoded in `email_service.py`) |
| Subject includes visibility score | Task 5 (`overall_score:.0f` in subject f-string) |
| activity_log entry on send | Task 5 (`ActivityLog(event_type="digest_sent", ...)`) |
| Manual test trigger for Faris | Task 7 (`POST /api/v1/digest/trigger/{client_id}`) |
| Digest event shows in activity log UI | Task 8 (`digest_sent` label + `Mail` icon) |

### Placeholder Scan

No TBD / TODO / "implement later" found.

### Type Consistency

- `DigestData` dataclass fields used identically in `send_client_digest`, `_build_email_html`, and all tests ✓
- `_compute_trend(current: float, prev: float | None) -> str` — called with matching types in `_compute_digest_data` ✓
- `_detect_first_seen(seen_count: int, prev_scan: Scan | None, db: Session) -> bool` — called correctly ✓
- `get_digest_action(client, current_ai_citability, prev_ai_citability)` — called with `float | None` matching signature ✓
- `send_email(to, subject, html_body)` — keyword args match function signature in all call sites ✓
- `send_client_digest(client_id: uuid.UUID, db: Session) -> bool` — called correctly in both task functions ✓
- `ActivityLog(event_type="digest_sent", ...)` — `event_type` is `str`, `note` is `str`, matches model ✓
- `DIGEST_STATIC_TIPS` keys (`"excellent"`, `"good"`, `"fair"`, `"developing"`, `"low"`) match all possible return values of `_score_band()` which iterates `SCORE_BANDS` ✓
