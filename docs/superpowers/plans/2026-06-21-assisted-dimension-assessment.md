# Assisted Dimension Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the admin generate a Claude-suggested, evidence-backed score for Brand Authority and Content Quality, review it, and accept/adjust before it counts — replacing the bare "Assessed by SeenBy team" number with a defensible, evidence-backed one.

**Architecture:** A new `AssessmentService` calls the Claude API with rubric prompts (condensed from the `geo-brand-mentions` and `geo-content` skills), returning `{score, bullets[], narrative}`. The suggestion is stored as a `DimensionAssessment` row (status `suggested`). On accept, the score is written to the existing `client.brand_authority_score` / `content_quality_score` fields (where `compute_geo_score` already reads it) plus a denormalized evidence text to `client.*_evidence`; the row stays canonical for the structured bullets + audit history. The client view reads the accepted bullets and shows them under a new label.

**Tech Stack:** FastAPI, SQLAlchemy (sync), Alembic, Anthropic SDK, Pydantic v2, pytest (SQLite in-memory), Next.js 15 / React / TypeScript, shadcn/ui.

## Global Constraints

- **Language rules (CLAUDE.md §2)** — never surface: cited/uncited, mentioned/not mentioned, citation rate, ranking position, visibility gap, confidence score, char offset, token count, first mentioned. Use: "Seen by AI / Not seen by AI", "visibility frequency", "AI Search Ranking", "Your competitors are winning here", "first seen by AI".
- **Client-facing label:** `Based on public evidence · Reviewed by SeenBy` (exact string).
- **`SCORE_VERSION` → `v1.2.0`** (was `v1.1.0`). Weights/formula unchanged.
- **Dimensions are exactly:** `brand_authority`, `content_quality`.
- **Backend conventions (CLAUDE.md §10):** routes in `app/api/v1/`, business logic in `app/services/`, constants in `app/core/constants.py`, one model file per entity, Alembic migration for every schema change (no raw ALTER).
- **Never expose to client-facing surfaces:** `raw_narrative`, confidence scores, char offsets, token counts, raw API responses.
- **Claude calls:** use `anthropic_client()` + `record_llm_call(...)` immediately after, model `MODEL` (`claude-haiku-4-5-20251001`). Retry-once-then-flag; on unparseable output persist nothing and surface a retryable error.
- **MVP boundary:** this ships as *assisted, human-reviewed* scoring (admin gates every number) — NOT fully automated scoring.

---

## File Structure

**Backend — create**
- `app/models/dimension_assessment.py` — `DimensionAssessment` model
- `alembic/versions/c3d4e5f6a7b8_create_dimension_assessments.py` — migration
- `app/prompts/assessment.py` — prompt builders + version constants
- `app/services/assessment_service.py` — generate/accept/sanitize logic
- `app/schemas/assessment.py` — request/response schemas
- `tests/test_assessment_service.py`, `tests/test_assessment_endpoints.py`

**Backend — modify**
- `tests/conftest.py:9` — register the new model for test `create_all`
- `app/prompts/registry.py` — register the two assessment services
- `app/core/constants.py` — `SCORE_VERSION` bump + dimension/status/label constants
- `app/api/v1/clients.py` — 3 endpoints
- `app/schemas/client_view.py` — evidence-bullet fields + docstring
- `app/api/v1/client_view.py` — populate bullets in the overview
- `app/services/report_service.py:744` — label swap

**Frontend — modify**
- `src/types/index.ts` — assessment types
- `src/lib/api.ts` — assessment API calls
- `src/app/clients/[id]/settings/SettingsForm.tsx` — generate/review UI + label swap
- `src/app/clients/[id]/page.tsx:173` — label swap
- `src/app/clients/[id]/checklist/ChecklistClient.tsx:97,102` — label swap
- `src/app/view/[token]/page.tsx:258` — render bullets + label swap

**Docs — modify**
- root `CLAUDE.md` §4 + §11

---

## Task 1: DimensionAssessment model + migration

**Files:**
- Create: `app/models/dimension_assessment.py`
- Create: `alembic/versions/c3d4e5f6a7b8_create_dimension_assessments.py`
- Modify: `tests/conftest.py:9`
- Test: `tests/test_assessment_service.py` (model-shape test only in this task)

**Interfaces:**
- Produces: `DimensionAssessment(id, client_id, dimension, suggested_score, final_score, evidence_bullets, raw_narrative, status, generated_at, reviewed_at)` SQLAlchemy model on `Base.metadata`, table `dimension_assessments`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_assessment_service.py`:

```python
import uuid
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.my", industry="dentist")
    db.add(c)
    db.commit()
    return c


def test_dimension_assessment_row_roundtrips(db):
    c = _client(db)
    row = DimensionAssessment(
        client_id=c.id,
        dimension="brand_authority",
        suggested_score=58,
        evidence_bullets=["Active on Reddit in 3 relevant communities"],
        raw_narrative="full reasoning",
        status="suggested",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id is not None
    assert row.final_score is None
    assert row.evidence_bullets == ["Active on Reddit in 3 relevant communities"]
    assert row.status == "suggested"
    assert row.generated_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_assessment_service.py::test_dimension_assessment_row_roundtrips -v`
Expected: FAIL with `ModuleNotFoundError: app.models.dimension_assessment`.

- [ ] **Step 3: Create the model**

Create `app/models/dimension_assessment.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DimensionAssessment(Base):
    """Claude-suggested, admin-reviewed score for a manual GEO dimension
    (brand_authority | content_quality).

    The accepted value also lives on the Client row (where compute_geo_score
    reads it); this table is canonical for the structured evidence bullets and
    the audit trail (suggested vs final, when reviewed). raw_narrative is
    ADMIN-ONLY and must never reach a client-facing schema.
    """
    __tablename__ = "dimension_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_score: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_bullets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="suggested")
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 4: Register the model for tests**

In `tests/conftest.py`, line 9, append `, dimension_assessment` to the `from app.models import ...` list:

```python
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment  # noqa: F401
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_assessment_service.py::test_dimension_assessment_row_roundtrips -v`
Expected: PASS.

- [ ] **Step 6: Write the Alembic migration**

Create `alembic/versions/c3d4e5f6a7b8_create_dimension_assessments.py`:

```python
"""create_dimension_assessments_table

Revision ID: c3d4e5f6a7b8
Revises: b2f3c4d5e6a7
Create Date: 2026-06-21 08:20:00.000000

Stores Claude-suggested, admin-reviewed scores + evidence for the manual GEO
dimensions (brand_authority, content_quality).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2f3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dimension_assessments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('dimension', sa.String(length=32), nullable=False),
        sa.Column('suggested_score', sa.Integer(), nullable=False),
        sa.Column('final_score', sa.Integer(), nullable=True),
        sa.Column('evidence_bullets', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('raw_narrative', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='suggested'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dimension_assessments_client_id', 'dimension_assessments', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_dimension_assessments_client_id', table_name='dimension_assessments')
    op.drop_table('dimension_assessments')
```

- [ ] **Step 7: Apply and verify the migration**

Run: `cd backend && alembic upgrade head && alembic current`
Expected: head is `c3d4e5f6a7b8`. No errors.

- [ ] **Step 8: Commit**

```bash
git add app/models/dimension_assessment.py alembic/versions/c3d4e5f6a7b8_create_dimension_assessments.py tests/conftest.py tests/test_assessment_service.py
git commit -m "feat(assessment): DimensionAssessment model + migration"
```

---

## Task 2: Constants — score version, dimension/status/label

**Files:**
- Modify: `app/core/constants.py`
- Test: `tests/test_assessment_service.py`

**Interfaces:**
- Produces: `SCORE_VERSION == "v1.2.0"`; `DIMENSION_BRAND_AUTHORITY`, `DIMENSION_CONTENT_QUALITY`, `ASSESSABLE_DIMENSIONS`, `ASSESSMENT_STATUSES`, `DIMENSION_EVIDENCE_LABEL`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_service.py`:

```python
from app.core import constants


def test_assessment_constants_present():
    assert constants.SCORE_VERSION == "v1.2.0"
    assert constants.ASSESSABLE_DIMENSIONS == ("brand_authority", "content_quality")
    assert constants.ASSESSMENT_STATUSES == ("suggested", "accepted", "adjusted")
    assert constants.DIMENSION_EVIDENCE_LABEL == "Based on public evidence · Reviewed by SeenBy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_assessment_service.py::test_assessment_constants_present -v`
Expected: FAIL (`SCORE_VERSION == "v1.1.0"`, attrs missing).

- [ ] **Step 3: Edit constants**

In `app/core/constants.py`, change the `SCORE_VERSION` line to:

```python
SCORE_VERSION: Final = "v1.2.0"  # v1.2.0: Brand Authority & Content Quality are Claude-suggested, admin-reviewed (assisted scoring); weights unchanged
```

Append near the other dimension-related constants:

```python
# Manual GEO dimensions that support Claude-assisted, admin-reviewed scoring.
DIMENSION_BRAND_AUTHORITY: Final = "brand_authority"
DIMENSION_CONTENT_QUALITY: Final = "content_quality"
ASSESSABLE_DIMENSIONS: Final = (DIMENSION_BRAND_AUTHORITY, DIMENSION_CONTENT_QUALITY)
ASSESSMENT_STATUSES: Final = ("suggested", "accepted", "adjusted")
# Client-facing label replacing "Assessed by SeenBy team" — leads with verifiability.
DIMENSION_EVIDENCE_LABEL: Final = "Based on public evidence · Reviewed by SeenBy"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_assessment_service.py::test_assessment_constants_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/constants.py tests/test_assessment_service.py
git commit -m "feat(assessment): score-version bump + dimension/label constants"
```

---

## Task 3: Prompt module + registry

**Files:**
- Create: `app/prompts/assessment.py`
- Modify: `app/prompts/registry.py`
- Test: `tests/test_assessment_service.py`

**Interfaces:**
- Produces: `build_assessment_prompt(client, dimension) -> str`; `BRAND_AUTHORITY_VERSION`, `CONTENT_QUALITY_VERSION`. Registry keys `assessment_brand_authority`, `assessment_content_quality`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_service.py`:

```python
from app.prompts import assessment as assessment_prompts


def test_prompt_includes_business_and_json_contract(db):
    c = _client(db)
    p = assessment_prompts.build_assessment_prompt(c, "brand_authority")
    assert "Acme" in p and "dentist" in p
    assert '"score"' in p and '"bullets"' in p and '"narrative"' in p
    # language rules surfaced to the model
    assert "seen by AI" in p.lower()


def test_prompt_rejects_unknown_dimension(db):
    c = _client(db)
    try:
        assessment_prompts.build_assessment_prompt(c, "made_up")
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k prompt -v`
Expected: FAIL (`app.prompts.assessment` missing).

- [ ] **Step 3: Create the prompt module**

Create `app/prompts/assessment.py`:

```python
# backend/app/prompts/assessment.py
"""Prompt templates for Claude-assisted dimension assessment.

Condensed from the geo-brand-mentions (Brand Authority) and geo-content /
E-E-A-T (Content Quality) rubrics. Each prompt asks Claude to assess the
client's PUBLIC web/brand footprint and return a strict JSON contract.
"""
from app.models.client import Client
from app.core.constants import DIMENSION_BRAND_AUTHORITY, DIMENSION_CONTENT_QUALITY

BRAND_AUTHORITY_VERSION = "v1"
CONTENT_QUALITY_VERSION = "v1"

_LANGUAGE_RULES = (
    'Never use the words "citation", "cited", "mentioned", "citation rate", '
    '"ranking position", or "visibility gap". Use "seen by AI", "visibility '
    'frequency", and "AI Search Ranking" instead.'
)

_JSON_CONTRACT = (
    'Output ONLY valid JSON, no code fences, exactly:\n'
    '{{"score": <integer 0-100>, "bullets": ["3-5 short plain-English evidence '
    'points a non-technical client would understand"], "narrative": "2-3 '
    'sentence internal rationale"}}'
)


def _location(client: Client) -> str:
    return ", ".join(p for p in (client.city, client.state, client.country) if p)


def _brand_authority_prompt(client: Client) -> str:
    loc = _location(client)
    return f"""You assess the BRAND AUTHORITY of a {client.industry} business called {client.name}{f" based in {loc}" if loc else ""} for AI search visibility.
Website: {client.website}. Business context: {client.description or "n/a"}.

Brand Authority measures how strongly AI models recognise this brand as a real, trusted entity, based on PUBLIC signals an outsider could verify:
- Presence and engagement on high-AI-weight platforms (YouTube, Reddit, Wikipedia/Wikidata, LinkedIn).
- Third-party reviews and directory listings (Google, G2, Trustpilot, industry directories).
- Branded search demand and consistent name/usage across the web.

Score 0-100 where 80-100 = a widely-recognised authority, 50-64 = present but thin, 0-34 = almost no public footprint.
Each bullet must state an observable, public fact (e.g. "Listed on Google with 40+ reviews at 4.6 stars"), never an internal metric.
{_LANGUAGE_RULES}
{_JSON_CONTRACT}"""


def _content_quality_prompt(client: Client) -> str:
    loc = _location(client)
    return f"""You assess the CONTENT QUALITY (E-E-A-T) of a {client.industry} business called {client.name}{f" based in {loc}" if loc else ""} for AI search visibility.
Website: {client.website}. Business context: {client.description or "n/a"}.

Content Quality measures whether the website's content demonstrates Experience, Expertise, Authoritativeness, and Trustworthiness, and is structured so AI can extract and reuse it:
- Visible author credentials / bios; first-hand experience and original data.
- Depth, accurate use of industry terminology, cited sources.
- Clear structure (headings, FAQs), freshness, and trust signals (contact, policies).

Score 0-100 where 80-100 = strong, well-structured expert content, 50-64 = adequate but shallow, 0-34 = thin or generic.
Each bullet must state an observable, public fact (e.g. "Author bios with credentials on all blog posts"), never an internal metric.
{_LANGUAGE_RULES}
{_JSON_CONTRACT}"""


_BUILDERS = {
    DIMENSION_BRAND_AUTHORITY: _brand_authority_prompt,
    DIMENSION_CONTENT_QUALITY: _content_quality_prompt,
}


def build_assessment_prompt(client: Client, dimension: str) -> str:
    if dimension not in _BUILDERS:
        raise ValueError(f"unknown dimension: {dimension}")
    return _BUILDERS[dimension](client)
```

- [ ] **Step 4: Register in the prompt registry**

In `app/prompts/registry.py`, add `assessment` to the `from app.prompts import (...)` block, and add two registry entries:

```python
    "assessment_brand_authority":  {"version": assessment.BRAND_AUTHORITY_VERSION,  "model": MODEL},
    "assessment_content_quality":  {"version": assessment.CONTENT_QUALITY_VERSION,  "model": MODEL},
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k prompt -v`
Expected: PASS (both).

- [ ] **Step 6: Commit**

```bash
git add app/prompts/assessment.py app/prompts/registry.py tests/test_assessment_service.py
git commit -m "feat(assessment): rubric prompts + registry entries"
```

---

## Task 4: AssessmentService — generate + sanitize

**Files:**
- Create: `app/services/assessment_service.py`
- Test: `tests/test_assessment_service.py`

**Interfaces:**
- Consumes: `build_assessment_prompt` (Task 3); `DimensionAssessment` (Task 1); `anthropic_client`, `strip_code_fences`, `MODEL`, `record_llm_call`.
- Produces:
  - `sanitize_bullets(bullets: list[str]) -> list[str]`
  - `generate_assessment(client: Client, dimension: str, db: Session) -> DimensionAssessment | None` (None on Claude failure / unparseable output; nothing persisted)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_assessment_service.py`:

```python
from unittest.mock import patch, MagicMock
from app.services import assessment_service


def test_sanitize_bullets_replaces_forbidden_terms():
    out = assessment_service.sanitize_bullets([
        "Brand was mentioned in 3 articles",
        "Strong citation rate on Reddit",
    ])
    joined = " ".join(out).lower()
    assert "mentioned" not in joined
    assert "citation rate" not in joined
    assert "seen by ai" in joined


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=10, output_tokens=20)
    return resp


def test_generate_assessment_persists_suggested_row(db):
    c = _client(db)
    payload = '{"score": 58, "bullets": ["Listed on Google with 40 reviews"], "narrative": "ok"}'
    with patch.object(assessment_service, "anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response(payload)
        row = assessment_service.generate_assessment(c, "brand_authority", db)
    assert row is not None
    assert row.status == "suggested"
    assert row.suggested_score == 58
    assert row.final_score is None
    assert row.evidence_bullets == ["Listed on Google with 40 reviews"]
    assert row.raw_narrative == "ok"


def test_generate_assessment_returns_none_on_bad_json(db):
    c = _client(db)
    with patch.object(assessment_service, "anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response("not json")
        row = assessment_service.generate_assessment(c, "brand_authority", db)
    assert row is None
    assert db.query(DimensionAssessment).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k "generate or sanitize" -v`
Expected: FAIL (`app.services.assessment_service` missing).

- [ ] **Step 3: Implement the service (generate + sanitize)**

Create `app/services/assessment_service.py`:

```python
# backend/app/services/assessment_service.py
"""Claude-assisted, admin-reviewed scoring for the manual GEO dimensions."""
import json
import re
from datetime import datetime

import structlog
from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.prompts.assessment import build_assessment_prompt
from app.services.claude_client import anthropic_client, strip_code_fences, MODEL
from app.services.cost_tracker import record_llm_call

logger = structlog.get_logger()

_MAX_TOKENS = 800

# CLAUDE.md §2 — case-insensitive replacements applied to client-facing bullets
# as a safety net behind the prompt's own instructions.
_FORBIDDEN: list[tuple[str, str]] = [
    (r"\bnot mentioned\b", "not seen by AI"),
    (r"\buncited\b", "not seen by AI"),
    (r"\bmentioned\b", "seen by AI"),
    (r"\bcited\b", "seen by AI"),
    (r"\bcitation rate\b", "visibility frequency"),
    (r"\branking position\b", "AI Search Ranking"),
    (r"\bvisibility gap\b", "Your competitors are winning here"),
    (r"\bfirst mentioned\b", "first seen by AI"),
]

_SERVICE_BY_DIMENSION = {
    "brand_authority": "assessment_brand_authority",
    "content_quality": "assessment_content_quality",
}


def sanitize_bullets(bullets: list[str]) -> list[str]:
    """Replace forbidden vocabulary; drop empties. Never raises."""
    cleaned: list[str] = []
    for raw in bullets:
        text = str(raw).strip()
        for pattern, repl in _FORBIDDEN:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        if text:
            cleaned.append(text)
    return cleaned


def generate_assessment(client: Client, dimension: str, db: Session) -> DimensionAssessment | None:
    """Run the Claude assessment for one dimension and persist a `suggested` row.

    Returns None when Claude fails or returns unparseable output — caller
    surfaces a retryable error; nothing is persisted in that case.
    """
    service = _SERVICE_BY_DIMENSION[dimension]
    try:
        response = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": build_assessment_prompt(client, dimension)}],
        )
        record_llm_call(service=service, model=MODEL, response=response, client_id=client.id, db=db)
        payload = json.loads(strip_code_fences(response.content[0].text))
        score = int(payload["score"])
        score = max(0, min(100, score))
        bullets = sanitize_bullets(payload["bullets"])
        narrative = str(payload.get("narrative", "")).strip() or None
        if not bullets:
            raise ValueError("assessment produced no usable evidence bullets")
    except Exception as exc:
        logger.warning(
            "assessment_generation_failed",
            client_id=str(client.id), dimension=dimension, error=str(exc),
        )
        return None

    row = DimensionAssessment(
        client_id=client.id,
        dimension=dimension,
        suggested_score=score,
        evidence_bullets=bullets,
        raw_narrative=narrative,
        status="suggested",
        generated_at=datetime.utcnow(),
    )
    db.add(row)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="assessment_generated",
        note=f"{dimension} assessment generated (suggested {score})",
    ))
    db.commit()
    db.refresh(row)
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k "generate or sanitize" -v`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add app/services/assessment_service.py tests/test_assessment_service.py
git commit -m "feat(assessment): generate suggested scores + language sanitizer"
```

---

## Task 5: AssessmentService — accept

**Files:**
- Modify: `app/services/assessment_service.py`
- Test: `tests/test_assessment_service.py`

**Interfaces:**
- Consumes: `DimensionAssessment`, `Client`.
- Produces: `accept_assessment(client: Client, dimension: str, final_score: int | None, db: Session) -> DimensionAssessment | None`. Writes `client.<dimension>_score` and `client.<dimension>_evidence` (bullets joined by newline). `final_score=None` accepts the suggested score (status `accepted`); a different value sets status `adjusted`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_assessment_service.py`:

```python
def _suggested_row(db, client, dimension="brand_authority", score=58):
    row = DimensionAssessment(
        client_id=client.id, dimension=dimension, suggested_score=score,
        evidence_bullets=["Listed on Google with 40 reviews", "Active subreddit presence"],
        raw_narrative="n", status="suggested",
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_accept_writes_through_to_client(db):
    c = _client(db)
    _suggested_row(db, c, score=58)
    row = assessment_service.accept_assessment(c, "brand_authority", None, db)
    db.refresh(c)
    assert row.status == "accepted"
    assert row.final_score == 58
    assert row.reviewed_at is not None
    assert c.brand_authority_score == 58
    assert "Listed on Google with 40 reviews" in (c.brand_authority_evidence or "")


def test_accept_with_adjusted_score_marks_adjusted(db):
    c = _client(db)
    _suggested_row(db, c, score=58)
    row = assessment_service.accept_assessment(c, "brand_authority", 65, db)
    db.refresh(c)
    assert row.status == "adjusted"
    assert row.final_score == 65
    assert c.brand_authority_score == 65


def test_accept_without_suggestion_returns_none(db):
    c = _client(db)
    assert assessment_service.accept_assessment(c, "content_quality", None, db) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k accept -v`
Expected: FAIL (`accept_assessment` not defined).

- [ ] **Step 3: Implement accept**

Append to `app/services/assessment_service.py`:

```python
from sqlalchemy import desc

_SCORE_FIELD = {
    "brand_authority": "brand_authority_score",
    "content_quality": "content_quality_score",
}
_EVIDENCE_FIELD = {
    "brand_authority": "brand_authority_evidence",
    "content_quality": "content_quality_evidence",
}


def latest_assessment(client_id, dimension: str, db: Session) -> DimensionAssessment | None:
    return (
        db.query(DimensionAssessment)
        .filter(DimensionAssessment.client_id == client_id,
                DimensionAssessment.dimension == dimension)
        .order_by(desc(DimensionAssessment.generated_at))
        .first()
    )


def accept_assessment(
    client: Client, dimension: str, final_score: int | None, db: Session
) -> DimensionAssessment | None:
    """Accept (or adjust) the latest suggestion for a dimension.

    Writes the accepted score + denormalized evidence text to the Client row so
    the existing evidence-required invariant and the PDF report keep working.
    Does NOT create a GeoScore row — the value flows into the overall score at
    the next scan, identical to a manual dimension edit today. Returns None when
    there is no suggestion to accept.
    """
    row = latest_assessment(client.id, dimension, db)
    if row is None:
        return None

    accepted = row.suggested_score if final_score is None else max(0, min(100, int(final_score)))
    row.final_score = accepted
    row.status = "accepted" if accepted == row.suggested_score else "adjusted"
    row.reviewed_at = datetime.utcnow()

    setattr(client, _SCORE_FIELD[dimension], accepted)
    setattr(client, _EVIDENCE_FIELD[dimension], "\n".join(row.evidence_bullets))

    db.add(ActivityLog(
        client_id=client.id,
        event_type="assessment_accepted",
        note=f"{dimension} score set to {accepted} ({row.status})",
    ))
    db.commit()
    db.refresh(row)
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_assessment_service.py -k accept -v`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add app/services/assessment_service.py tests/test_assessment_service.py
git commit -m "feat(assessment): accept/adjust writes accepted score through to client"
```

---

## Task 6: API schemas + endpoints

**Files:**
- Create: `app/schemas/assessment.py`
- Modify: `app/api/v1/clients.py`
- Test: `tests/test_assessment_endpoints.py`

**Interfaces:**
- Consumes: `generate_assessment`, `accept_assessment`, `latest_assessment` (Tasks 4–5); `ASSESSABLE_DIMENSIONS`.
- Produces (admin, `require_api_key`):
  - `POST /clients/{id}/assessments/{dimension}/generate` → `AssessmentResponse` (502 on Claude failure)
  - `POST /clients/{id}/assessments/{dimension}/accept` body `AcceptRequest{final_score?: int}` → `AssessmentResponse`
  - `GET /clients/{id}/assessments` → `list[AssessmentResponse]` (latest per dimension)
  - Unknown dimension → 422.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_assessment_endpoints.py`:

```python
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.core.security import require_api_key
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment


def _setup(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_api_key] = lambda: None


def _client_row(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.my", industry="dentist")
    db.add(c); db.commit()
    return c


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=10, output_tokens=20)
    return resp


def test_generate_endpoint_returns_draft(db):
    _setup(db)
    c = _client_row(db)
    payload = '{"score": 58, "bullets": ["Listed on Google with 40 reviews"], "narrative": "ok"}'
    with patch("app.services.assessment_service.anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response(payload)
        r = TestClient(app).post(f"/api/v1/clients/{c.id}/assessments/brand_authority/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["suggested_score"] == 58
    assert body["status"] == "suggested"
    assert body["final_score"] is None
    app.dependency_overrides.clear()


def test_generate_unknown_dimension_422(db):
    _setup(db)
    c = _client_row(db)
    r = TestClient(app).post(f"/api/v1/clients/{c.id}/assessments/nope/generate")
    assert r.status_code == 422
    app.dependency_overrides.clear()


def test_generate_failure_returns_502(db):
    _setup(db)
    c = _client_row(db)
    with patch("app.services.assessment_service.anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response("not json")
        r = TestClient(app).post(f"/api/v1/clients/{c.id}/assessments/brand_authority/generate")
    assert r.status_code == 502
    app.dependency_overrides.clear()


def test_accept_endpoint_writes_score(db):
    _setup(db)
    c = _client_row(db)
    db.add(DimensionAssessment(
        client_id=c.id, dimension="brand_authority", suggested_score=58,
        evidence_bullets=["Listed on Google with 40 reviews"], status="suggested",
    ))
    db.commit()
    r = TestClient(app).post(
        f"/api/v1/clients/{c.id}/assessments/brand_authority/accept", json={"final_score": 65}
    )
    assert r.status_code == 200
    assert r.json()["final_score"] == 65
    db.refresh(c)
    assert c.brand_authority_score == 65
    app.dependency_overrides.clear()
```

> If `app.core.security.require_api_key` lives elsewhere, adjust the import to match `clients.py`'s `from app.core... import require_api_key`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_assessment_endpoints.py -v`
Expected: FAIL (routes 404 / schema missing).

- [ ] **Step 3: Create the schemas**

Create `app/schemas/assessment.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AcceptRequest(BaseModel):
    # None = accept the suggested score as-is; a value adjusts it.
    final_score: int | None = None


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dimension: str
    suggested_score: int
    final_score: int | None
    status: str
    evidence_bullets: list[str]
    raw_narrative: str | None  # admin-only surface; never used by client view
    generated_at: datetime
    reviewed_at: datetime | None
```

- [ ] **Step 4: Add the endpoints**

In `app/api/v1/clients.py`, add imports:

```python
from app.core.constants import ASSESSABLE_DIMENSIONS
from app.schemas.assessment import AcceptRequest, AssessmentResponse
from app.services import assessment_service
```

Append these routes (after the geo-score route):

```python
def _require_dimension(dimension: str) -> None:
    if dimension not in ASSESSABLE_DIMENSIONS:
        raise HTTPException(status_code=422, detail="Unknown dimension.")


@router.post(
    "/{client_id}/assessments/{dimension}/generate",
    response_model=AssessmentResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_assessment(client_id: uuid.UUID, dimension: str, db: Session = Depends(get_db)):
    _require_dimension(dimension)
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    row = assessment_service.generate_assessment(c, dimension, db)
    if row is None:
        raise HTTPException(status_code=502, detail="Assessment failed — please try again.")
    return row


@router.post(
    "/{client_id}/assessments/{dimension}/accept",
    response_model=AssessmentResponse,
    dependencies=[Depends(require_api_key)],
)
def accept_assessment(
    client_id: uuid.UUID, dimension: str, body: AcceptRequest, db: Session = Depends(get_db)
):
    _require_dimension(dimension)
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    row = assessment_service.accept_assessment(c, dimension, body.final_score, db)
    if row is None:
        raise HTTPException(status_code=404, detail="No assessment to accept — generate one first.")
    return row


@router.get(
    "/{client_id}/assessments",
    response_model=list[AssessmentResponse],
    dependencies=[Depends(require_api_key)],
)
def list_assessments(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return [
        row for dimension in ASSESSABLE_DIMENSIONS
        if (row := assessment_service.latest_assessment(client_id, dimension, db)) is not None
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_assessment_endpoints.py -v`
Expected: PASS (all 4).

- [ ] **Step 6: Commit**

```bash
git add app/schemas/assessment.py app/api/v1/clients.py tests/test_assessment_endpoints.py
git commit -m "feat(assessment): generate/accept/list endpoints"
```

---

## Task 7: Surface evidence bullets in the client view

**Files:**
- Modify: `app/schemas/client_view.py`
- Modify: `app/api/v1/client_view.py`
- Test: `tests/test_assessment_endpoints.py` (client-view assertion)

**Interfaces:**
- Consumes: `latest_assessment` (Task 5); `ClientViewScore` (existing).
- Produces: `ClientViewScore.brand_authority_evidence: list[str]`, `ClientViewScore.content_quality_evidence: list[str]` — populated only from `status in (accepted, adjusted)` rows; empty list otherwise. `raw_narrative` never included.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_endpoints.py`:

```python
def test_client_view_exposes_bullets_not_narrative(db):
    from app.models.geo_score import GeoScore
    from app.models.scan import Scan
    _setup(db)
    c = _client_row(db)
    c.share_token = "tok_" + uuid.uuid4().hex
    scan = Scan(id=uuid.uuid4(), client_id=c.id, platform="multi", status="completed")
    db.add(scan); db.commit()
    db.add(GeoScore(client_id=c.id, scan_id=scan.id, overall_score=70, ai_citability=60,
                    brand_authority=65, content_quality=50, technical_foundations=100,
                    structured_data=100))
    db.add(DimensionAssessment(
        client_id=c.id, dimension="brand_authority", suggested_score=65, final_score=65,
        evidence_bullets=["Listed on Google with 40 reviews"], raw_narrative="SECRET",
        status="accepted",
    ))
    db.commit()
    r = TestClient(app).get(f"/api/v1/view/{c.share_token}")
    assert r.status_code == 200
    assert "SECRET" not in r.text
    score = r.json()["latest_score"]
    assert "Listed on Google with 40 reviews" in score["brand_authority_evidence"]
    app.dependency_overrides.clear()
```

> Adjust `Scan(...)` kwargs to match the real model's required columns if the test errors on construction.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_assessment_endpoints.py::test_client_view_exposes_bullets_not_narrative -v`
Expected: FAIL (`brand_authority_evidence` KeyError).

- [ ] **Step 3: Extend the schema**

In `app/schemas/client_view.py`, add two fields to `ClientViewScore`:

```python
    brand_authority_evidence: list[str] = []
    content_quality_evidence: list[str] = []
```

Update the module docstring: change "evidence text" in the "Structurally excluded" list to clarify only `raw_narrative` and admin free-text are excluded — sanitized, accepted evidence bullets are deliberately surfaced.

- [ ] **Step 4: Populate in the view builder**

In `app/api/v1/client_view.py`, add a helper near the top of the module:

```python
from app.services.assessment_service import latest_assessment


def _accepted_bullets(db, client_id, dimension):
    row = latest_assessment(client_id, dimension, db)
    if row is not None and row.status in ("accepted", "adjusted"):
        return list(row.evidence_bullets)
    return []
```

In the `ClientViewScore(...)` construction (around line 275), add:

```python
            brand_authority_evidence=_accepted_bullets(db, client.id, "brand_authority"),
            content_quality_evidence=_accepted_bullets(db, client.id, "content_quality"),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_assessment_endpoints.py::test_client_view_exposes_bullets_not_narrative -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS (no regressions). The pre-existing `test_rate_limit` X-Forwarded-For failure noted in project history is unrelated.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/client_view.py app/api/v1/client_view.py tests/test_assessment_endpoints.py
git commit -m "feat(assessment): surface accepted evidence bullets in client view"
```

---

## Task 8: Frontend — types + API client

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/lib/api.ts`

**Interfaces:**
- Produces: `DimensionAssessment` type; `api.generateAssessment`, `api.acceptAssessment`, `api.listAssessments`.

- [ ] **Step 1: Add the type**

In `src/types/index.ts`, add:

```typescript
export type AssessmentDimension = "brand_authority" | "content_quality";

export interface DimensionAssessment {
  id: string;
  dimension: AssessmentDimension;
  suggested_score: number;
  final_score: number | null;
  status: "suggested" | "accepted" | "adjusted";
  evidence_bullets: string[];
  raw_narrative: string | null;
  generated_at: string;
  reviewed_at: string | null;
}
```

- [ ] **Step 2: Add the API calls**

In `src/lib/api.ts`, following the existing exported-function pattern in that file, add:

```typescript
export async function generateAssessment(clientId: string, dimension: AssessmentDimension) {
  return apiFetch<DimensionAssessment>(`/clients/${clientId}/assessments/${dimension}/generate`, {
    method: "POST",
  });
}

export async function acceptAssessment(
  clientId: string,
  dimension: AssessmentDimension,
  finalScore: number | null,
) {
  return apiFetch<DimensionAssessment>(`/clients/${clientId}/assessments/${dimension}/accept`, {
    method: "POST",
    body: JSON.stringify({ final_score: finalScore }),
  });
}

export async function listAssessments(clientId: string) {
  return apiFetch<DimensionAssessment[]>(`/clients/${clientId}/assessments`, { method: "GET" });
}
```

> Match the real helper name/signature in `api.ts` (e.g. `apiFetch`, `request`, or the `api` object). Import `DimensionAssessment`/`AssessmentDimension` from `@/types` if that file imports types explicitly.

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new type errors from these files.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(assessment): frontend types + API client"
```

---

## Task 9: Frontend — admin generate/review UI

**Files:**
- Modify: `src/app/clients/[id]/settings/SettingsForm.tsx`

**Interfaces:**
- Consumes: `generateAssessment`, `acceptAssessment`, `listAssessments`, `DimensionAssessment`.

- [ ] **Step 1: Add review state + a per-dimension control**

In `SettingsForm.tsx`, next to each existing manual-score input (Brand Authority near line 394, Content Quality near line ~485), render a "Generate assessment" button and, when a suggestion exists, a review card. Add this self-contained block once and reuse for both dimensions (pass `dimension` + the score setter):

```tsx
function AssessmentReview({
  clientId,
  dimension,
  onAccepted,
}: {
  clientId: string;
  dimension: AssessmentDimension;
  onAccepted: (score: number) => void;
}) {
  const [draft, setDraft] = useState<DimensionAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [adjust, setAdjust] = useState<string>("");

  async function generate() {
    setLoading(true);
    try {
      const a = await generateAssessment(clientId, dimension);
      setDraft(a);
      setAdjust(String(a.suggested_score));
    } catch {
      alert("Assessment failed — please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function accept(useAdjusted: boolean) {
    if (!draft) return;
    const finalScore = useAdjusted ? Number(adjust) : null;
    const saved = await acceptAssessment(clientId, dimension, finalScore);
    onAccepted(saved.final_score ?? saved.suggested_score);
    setDraft(null);
  }

  return (
    <div className="mt-2">
      <Button type="button" variant="outline" size="sm" onClick={generate} disabled={loading}>
        {loading ? "Assessing…" : "Generate assessment"}
      </Button>
      {draft && (
        <div className="mt-2 rounded-md border p-3 text-sm">
          <div className="font-medium">Suggested: {draft.suggested_score}</div>
          <ul className="ml-4 list-disc">
            {draft.evidence_bullets.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2">
            <Button type="button" size="sm" onClick={() => accept(false)}>
              Accept
            </Button>
            <input
              className="w-16 rounded border px-2 py-1"
              value={adjust}
              onChange={(e) => setAdjust(e.target.value)}
            />
            <Button type="button" size="sm" variant="secondary" onClick={() => accept(true)}>
              Adjust &amp; accept
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

Wire `onAccepted` to the existing brand-authority / content-quality score state setters so the form's number reflects the accepted value, and the existing evidence textarea is repopulated on next load (the backend writes it through).

- [ ] **Step 2: Swap the label**

Replace the "Assessed by SeenBy team" copy in this file (lines ~394, ~485, ~501) with `Based on public evidence · Reviewed by SeenBy`.

- [ ] **Step 3: Verify it compiles + smoke test**

Run: `cd frontend && npx tsc --noEmit`
Then with both dev servers running, open a client's settings, click **Generate assessment**, confirm a suggestion + bullets render and **Accept** updates the score.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/clients/[id]/settings/SettingsForm.tsx
git commit -m "feat(assessment): admin generate/review UI in settings"
```

---

## Task 10: Frontend — client view bullets + label swap

**Files:**
- Modify: `src/app/view/[token]/page.tsx:258`
- Modify: `src/app/clients/[id]/page.tsx:173`
- Modify: `src/app/clients/[id]/checklist/ChecklistClient.tsx:97,102`

**Interfaces:**
- Consumes: `latest_score.brand_authority_evidence`, `latest_score.content_quality_evidence` (Task 7).

- [ ] **Step 1: Render bullets + label in the client view**

In `src/app/view/[token]/page.tsx`, replace the "Assessed by SeenBy team" span (line 258) with `Based on public evidence · Reviewed by SeenBy`, and under the Brand Authority and Content Quality rows render the bullets when present:

```tsx
{score.brand_authority_evidence?.length > 0 && (
  <ul className="ml-4 mt-1 list-disc text-sm text-muted-foreground">
    {score.brand_authority_evidence.map((b, i) => (
      <li key={i}>{b}</li>
    ))}
  </ul>
)}
```

Add the equivalent block for `content_quality_evidence` under the Content Quality row.

- [ ] **Step 2: Swap remaining admin-side labels**

Replace "Assessed by SeenBy team" with `Based on public evidence · Reviewed by SeenBy` in `src/app/clients/[id]/page.tsx:173` and `src/app/clients/[id]/checklist/ChecklistClient.tsx:97,102`.

- [ ] **Step 3: Verify + smoke test**

Run: `cd frontend && npx tsc --noEmit`
With dev servers up, open `/view/<token>` for a client with an accepted assessment; confirm bullets render under the new label and no internal text appears.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/view/[token]/page.tsx frontend/src/app/clients/[id]/page.tsx frontend/src/app/clients/[id]/checklist/ChecklistClient.tsx
git commit -m "feat(assessment): client-view evidence bullets + label swap"
```

---

## Task 11: PDF report label + CLAUDE.md reconciliation

**Files:**
- Modify: `app/services/report_service.py:744`
- Modify: root `CLAUDE.md` (§4, §11)

- [ ] **Step 1: Swap the PDF label**

In `report_service.py` line 744, change the cell text `Assessed by SeenBy team` to `Based on public evidence · Reviewed by SeenBy`. Keep the existing `manual-note` evidence rendering (it reads `client.*_evidence`, which accept now keeps populated).

- [ ] **Step 2: Run report tests**

Run: `cd backend && python -m pytest tests/ -k report -v`
Expected: PASS (update any test asserting the old label string to the new one).

- [ ] **Step 3: Update CLAUDE.md**

In root `CLAUDE.md`:
- §4 table: change Brand Authority and Content Quality `Source` from "Manual — admin input" to "Assisted — Claude-suggested, admin-reviewed"; change the manual-dimension label note from "Assessed by SeenBy team" to "Based on public evidence · Reviewed by SeenBy"; bump the `SCORE_VERSION` line to `v1.2.0` with the new changelog note.
- §11: remove "Automated Brand Authority or Content Quality scoring" from the do-not-build list, and add a one-line note: *Brand Authority / Content Quality shipped as assisted, human-reviewed scoring (admin gates every number) — fully automated scoring is still out of scope.*

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/report_service.py CLAUDE.md
git commit -m "docs(assessment): PDF label swap + CLAUDE.md reconciliation"
```

---

## Self-Review (completed during planning)

**Spec coverage:** engine (Tasks 3–4) ✓ · draft governance (Tasks 1, 5) ✓ · on-demand trigger (Task 6 generate endpoint + Task 9 button) ✓ · concise client evidence (Task 7 + Task 10) ✓ · `SCORE_VERSION` bump (Task 2) ✓ · label swap all 6 locations (Tasks 9–11) ✓ · CLAUDE.md edits (Task 11) ✓ · raw_narrative never client-facing (Task 7 test) ✓ · denormalized evidence text keeps `update_client` invariant + PDF working (Task 5) ✓ · no live GeoScore recompute (Task 5) ✓.

**Type consistency:** `generate_assessment` / `accept_assessment` / `latest_assessment` signatures match across service (Tasks 4–5), endpoints (Task 6), and client view (Task 7). `evidence_bullets: list[str]`, `status` values `suggested|accepted|adjusted`, dimension strings `brand_authority|content_quality` consistent backend↔frontend.

**Open implementer checks (flagged inline):** exact `require_api_key` import path in `clients.py`; the `api.ts` request-helper name; `Scan` model required columns in the Task 7 test. Each step notes the adjustment to make if the assumed name differs.
