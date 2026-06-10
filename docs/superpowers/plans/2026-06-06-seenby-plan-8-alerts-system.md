# SeenBy Plan 8: Alerts System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three alert types from the spec — score drop crossing alert, competitor overtake alert, and manual hallucination flag — plus rebuild the scan page frontend to display results and expose the flag button.

**Architecture:** A new `alert_service.py` handles all alert logic in one place. `scan_service.py` calls score-drop and competitor-overtake checks after each scan completes (wrapped in try/except so alert failures can't corrupt scan state). The hallucination flag is a `POST /api/v1/scans/{scan_id}/results/{result_id}/flag-hallucination` endpoint. The scan page (`/clients/[id]/scan`) is rebuilt from its stub with a client component that polls for scan status and renders query results with a flag button per row. All alerts email `contact@seenby.my` and write an `activity_log` entry.

**Tech Stack:** FastAPI · SQLAlchemy 2 · Resend (via existing `email_service.py`) · Next.js 15 · shadcn/ui · Lucide icons

---

## File Map

```
backend/
├── app/
│   ├── core/
│   │   └── constants.py                    MODIFY — add ALERTS_EMAIL
│   ├── services/
│   │   ├── alert_service.py                CREATE
│   │   └── scan_service.py                 MODIFY — call alert checks post-scan
│   ├── schemas/
│   │   └── scan.py                         MODIFY — add ScanQueryResultResponse, ScanWithResultsResponse
│   └── api/v1/
│       └── scans.py                        MODIFY — add /client/{client_id}/latest and /{scan_id}/results/{result_id}/flag-hallucination
└── tests/
    └── test_alert_service.py               CREATE

frontend/
└── src/
    ├── types/index.ts                      MODIFY — add Scan, ScanQueryResult types
    ├── lib/api.ts                          MODIFY — add getLatestScan, triggerScan, flagHallucination
    └── app/clients/[id]/
        ├── scan/
        │   ├── page.tsx                    MODIFY — rebuild from stub
        │   ├── ScanClient.tsx              CREATE
        │   └── actions.ts                  CREATE
        └── activity/page.tsx               MODIFY — add alert_sent, hallucination_flagged events
```

---

## Task 1: Add ALERTS_EMAIL Constant

**Files:**
- Modify: `backend/app/core/constants.py`

- [ ] **Step 1: Append ALERTS_EMAIL to constants.py**

Open `backend/app/core/constants.py`. Append at the end of the file:

```python
ALERTS_EMAIL: Final = "contact@seenby.my"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/core/constants.py
git commit -m "feat: add ALERTS_EMAIL constant"
```

---

## Task 2: Alert Service (TDD)

**Files:**
- Create: `backend/tests/test_alert_service.py`
- Create: `backend/app/services/alert_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_alert_service.py`:

```python
import uuid
import pytest
from unittest.mock import MagicMock, patch

from app.models.scan_query_result import ScanQueryResult
from app.models.scan import Scan
from app.models.client import Client


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(name="Test Brand", threshold=35):
    c = MagicMock(spec=Client)
    c.id = uuid.uuid4()
    c.name = name
    c.industry = "Technology"
    c.score_drop_threshold = threshold
    return c


def _make_geo_score(overall_score: float):
    gs = MagicMock()
    gs.overall_score = overall_score
    return gs


# ── check_score_drop_alert ────────────────────────────────────────────────────

def test_score_drop_fires_when_crosses_below_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(30.0), _make_geo_score(40.0), db)
    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "contact@seenby.my" == kwargs["to"]
    assert "Test Brand" in kwargs["subject"]
    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "alert_sent"
    assert "35" in added.note


def test_score_drop_does_not_fire_when_already_below_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        # prev=30, current=25 — both below threshold, no crossing
        check_score_drop_alert(client, _make_geo_score(25.0), _make_geo_score(30.0), db)
    mock_send.assert_not_called()
    db.commit.assert_not_called()


def test_score_drop_does_not_fire_when_both_above_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(40.0), _make_geo_score(50.0), db)
    mock_send.assert_not_called()


def test_score_drop_does_not_fire_on_first_scan():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(20.0), None, db)
    mock_send.assert_not_called()


def test_score_drop_fires_at_exact_threshold_boundary():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        # prev=35 (at threshold = was_above), current=34.9 (now_below)
        check_score_drop_alert(client, _make_geo_score(34.9), _make_geo_score(35.0), db)
    mock_send.assert_called_once()


# ── check_competitor_overtake_alert ──────────────────────────────────────────

def _make_results(n_detected: int, n_total: int, competitor_id=None):
    results = []
    for i in range(n_total):
        r = MagicMock()
        r.competitor_id = competitor_id
        r.brand_detected = i < n_detected
        results.append(r)
    return results


def test_competitor_overtake_fires_when_competitor_ahead():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id = uuid.uuid4()

    competitor = MagicMock()
    competitor.id = comp_id
    competitor.name = "Rival Corp"

    client_results = _make_results(2, 8, competitor_id=None)   # 25%
    comp_results = _make_results(3, 4, competitor_id=comp_id)  # 75%

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "Rival Corp" in kwargs["html_body"]
    assert "contact@seenby.my" == kwargs["to"]
    db.commit.assert_called_once()


def test_competitor_overtake_does_not_fire_when_client_ahead():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id = uuid.uuid4()

    competitor = MagicMock()
    competitor.id = comp_id
    competitor.name = "Small Rival"

    client_results = _make_results(6, 8, competitor_id=None)   # 75%
    comp_results = _make_results(1, 4, competitor_id=comp_id)  # 25%

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    mock_send.assert_not_called()
    db.commit.assert_not_called()


def test_competitor_overtake_does_not_fire_when_no_competitors():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, uuid.uuid4(), db)

    mock_send.assert_not_called()


def test_competitor_overtake_fires_once_per_winning_competitor():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id_a, comp_id_b = uuid.uuid4(), uuid.uuid4()

    comp_a = MagicMock(); comp_a.id = comp_id_a; comp_a.name = "Alpha"
    comp_b = MagicMock(); comp_b.id = comp_id_b; comp_b.name = "Beta"

    client_results = _make_results(2, 8, competitor_id=None)       # 25%
    comp_a_results = _make_results(3, 4, competitor_id=comp_id_a)  # 75% — wins
    comp_b_results = _make_results(1, 4, competitor_id=comp_id_b)  # 25% — tie (not > client)

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [comp_a, comp_b],
        client_results + comp_a_results + comp_b_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    assert mock_send.call_count == 1
    kwargs = mock_send.call_args[1]
    assert "Alpha" in kwargs["html_body"]


# ── flag_hallucination ────────────────────────────────────────────────────────

def test_flag_hallucination_sends_email_and_logs_activity():
    from app.services.alert_service import flag_hallucination

    result_id = uuid.uuid4()
    mock_result = MagicMock(spec=ScanQueryResult)
    mock_result.id = result_id
    mock_result.scan_id = uuid.uuid4()
    mock_result.query_text = "What is Test Brand known for?"
    mock_result.response_text = "Test Brand has no presence in the market."

    mock_scan = MagicMock(spec=Scan)
    mock_scan.client_id = uuid.uuid4()

    mock_client = MagicMock(spec=Client)
    mock_client.id = mock_scan.client_id
    mock_client.name = "Test Brand"

    db = MagicMock()
    db.get.side_effect = lambda model, val: {
        ScanQueryResult: mock_result,
        Scan: mock_scan,
        Client: mock_client,
    }[model]

    with patch("app.services.alert_service.send_email") as mock_send:
        flag_hallucination(result_id, db)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "contact@seenby.my" == kwargs["to"]
    assert "Test Brand" in kwargs["subject"]
    assert "What is Test Brand known for?" in kwargs["html_body"]

    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "hallucination_flagged"
    assert added.client_id == mock_client.id


def test_flag_hallucination_raises_when_result_not_found():
    from app.services.alert_service import flag_hallucination
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        flag_hallucination(uuid.uuid4(), db)
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend
pytest tests/test_alert_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.alert_service'`

- [ ] **Step 3: Create alert_service.py**

Create `backend/app/services/alert_service.py`:

```python
import uuid
from sqlalchemy.orm import Session
import structlog

from app.core.constants import ALERTS_EMAIL
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.email_service import send_email

logger = structlog.get_logger()


def check_score_drop_alert(
    client: Client,
    current_geo_score: GeoScore,
    prev_geo_score: GeoScore | None,
    db: Session,
) -> None:
    """Fires once when overall_score crosses below score_drop_threshold."""
    if prev_geo_score is None:
        return

    was_above = prev_geo_score.overall_score >= client.score_drop_threshold
    now_below = current_geo_score.overall_score < client.score_drop_threshold

    if not (was_above and now_below):
        return

    send_email(
        to=ALERTS_EMAIL,
        subject=f"Score drop alert: {client.name} — GEO Score dropped to {current_geo_score.overall_score:.0f}",
        html_body=_build_score_drop_email(
            client,
            current_geo_score.overall_score,
            prev_geo_score.overall_score,
        ),
    )
    db.add(ActivityLog(
        client_id=client.id,
        event_type="alert_sent",
        note=(
            f"Score drop alert sent. Overall GEO Score dropped from "
            f"{prev_geo_score.overall_score:.0f} to {current_geo_score.overall_score:.0f}, "
            f"crossing below threshold of {client.score_drop_threshold}."
        ),
    ))
    db.commit()
    logger.info("score_drop_alert_sent", client_id=str(client.id))


def check_competitor_overtake_alert(client: Client, scan_id: uuid.UUID, db: Session) -> None:
    """Fires for each competitor whose AI Citability now exceeds the client's."""
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    if not competitors:
        return

    all_results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == scan_id)
        .all()
    )

    client_results = [r for r in all_results if r.competitor_id is None]
    client_citability = _compute_citability(client_results)

    sent = False
    for competitor in competitors:
        comp_results = [r for r in all_results if r.competitor_id == competitor.id]
        comp_citability = _compute_citability(comp_results)
        if comp_citability > client_citability:
            delta = round(comp_citability - client_citability, 1)
            send_email(
                to=ALERTS_EMAIL,
                subject=f"Competitor overtake: {competitor.name} is ahead of {client.name}",
                html_body=_build_overtake_email(
                    client, competitor.name, comp_citability, client_citability, delta
                ),
            )
            db.add(ActivityLog(
                client_id=client.id,
                event_type="alert_sent",
                note=(
                    f"Competitor overtake alert: {competitor.name} AI visibility "
                    f"({comp_citability:.0f}%) now exceeds {client.name} ({client_citability:.0f}%). "
                    f"Delta: +{delta:.0f}%."
                ),
            ))
            sent = True

    if sent:
        db.commit()
        logger.info("competitor_overtake_alert_sent", client_id=str(client.id))


def flag_hallucination(result_id: uuid.UUID, db: Session) -> None:
    """Manual hallucination flag — called from the admin scan results panel."""
    result = db.get(ScanQueryResult, result_id)
    if not result:
        raise ValueError(f"Scan query result not found: {result_id}")

    scan = db.get(Scan, result.scan_id)
    client = db.get(Client, scan.client_id)

    send_email(
        to=ALERTS_EMAIL,
        subject=f"Hallucination flagged: {client.name}",
        html_body=_build_hallucination_email(client, result),
    )
    db.add(ActivityLog(
        client_id=client.id,
        event_type="hallucination_flagged",
        note=f"Hallucination flagged on query: {result.query_text[:100]}",
    ))
    db.commit()
    logger.info("hallucination_flagged", client_id=str(client.id), result_id=str(result_id))


def _compute_citability(results: list) -> float:
    if not results:
        return 0.0
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def _build_score_drop_email(client: Client, current: float, prev: float) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#dc2626;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Score Drop Alert</p>
          <p style="margin:4px 0 0;color:#fecaca;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#374151;">The overall GEO Score has crossed below the alert threshold.</p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Previous score</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{prev:.0f}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Current score</td>
              <td style="padding:8px 0;font-weight:600;color:#dc2626;text-align:right;">{current:.0f}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Alert threshold</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{client.score_drop_threshold}</td>
            </tr>
          </table>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:contact@seenby.my" style="color:#9ca3af;">contact@seenby.my</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_overtake_email(
    client: Client,
    competitor_name: str,
    comp_citability: float,
    client_citability: float,
    delta: float,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#f59e0b;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Competitor Overtake Alert</p>
          <p style="margin:4px 0 0;color:#fef3c7;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#374151;">
            <strong>{competitor_name}</strong> is now ahead in AI visibility.
            Your competitors are winning here.
          </p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">{client.name} AI visibility</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{client_citability:.0f}%</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">{competitor_name} AI visibility</td>
              <td style="padding:8px 0;font-weight:600;color:#f59e0b;text-align:right;">{comp_citability:.0f}%</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Gap</td>
              <td style="padding:8px 0;font-weight:600;color:#dc2626;text-align:right;">+{delta:.0f}% ahead</td>
            </tr>
          </table>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:contact@seenby.my" style="color:#9ca3af;">contact@seenby.my</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_hallucination_email(client: Client, result: ScanQueryResult) -> str:
    response_preview = (result.response_text or "")[:500]
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#7c3aed;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Hallucination Flagged</p>
          <p style="margin:4px 0 0;color:#ede9fe;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#6b7280;font-size:14px;font-weight:600;margin:0 0 8px;">Query</p>
          <p style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
                    padding:12px;font-size:14px;color:#374151;margin:0 0 16px;">
            {result.query_text}
          </p>
          <p style="color:#6b7280;font-size:14px;font-weight:600;margin:0 0 8px;">AI Response (excerpt)</p>
          <p style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
                    padding:12px;font-size:14px;color:#374151;margin:0 0 0;
                    white-space:pre-wrap;word-break:break-word;">
            {response_preview}
          </p>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:contact@seenby.my" style="color:#9ca3af;">contact@seenby.my</a>
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
pytest tests/test_alert_service.py -v
```

Expected:
```
test_score_drop_fires_when_crosses_below_threshold PASSED
test_score_drop_does_not_fire_when_already_below_threshold PASSED
test_score_drop_does_not_fire_when_both_above_threshold PASSED
test_score_drop_does_not_fire_on_first_scan PASSED
test_score_drop_fires_at_exact_threshold_boundary PASSED
test_competitor_overtake_fires_when_competitor_ahead PASSED
test_competitor_overtake_does_not_fire_when_client_ahead PASSED
test_competitor_overtake_does_not_fire_when_no_competitors PASSED
test_competitor_overtake_fires_once_per_winning_competitor PASSED
test_flag_hallucination_sends_email_and_logs_activity PASSED
test_flag_hallucination_raises_when_result_not_found PASSED
```

- [ ] **Step 5: Run full test suite — no regressions**

```bash
cd backend
pytest tests/ -v
```

Expected: all existing tests plus the 11 new alert tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_alert_service.py backend/app/services/alert_service.py
git commit -m "feat: add alert service — score drop, competitor overtake, hallucination flag"
```

---

## Task 3: Backend Schema + API Endpoints

**Files:**
- Modify: `backend/app/schemas/scan.py`
- Modify: `backend/app/api/v1/scans.py`

- [ ] **Step 1: Update scan.py schemas**

Replace the full contents of `backend/app/schemas/scan.py`:

```python
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


class ScanQueryResultResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    competitor_id: uuid.UUID | None = None
    competitor_name: str | None = None
    category: str
    query_text: str
    response_text: str | None = None
    brand_detected: bool
    created_at: datetime


class ScanWithResultsResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    platform: str
    status: str
    triggered_at: datetime
    completed_at: datetime | None = None
    results: list[ScanQueryResultResponse] = []
```

- [ ] **Step 2: Update scans.py with two new endpoints**

Replace the full contents of `backend/app/api/v1/scans.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.competitor import Competitor
from app.schemas.scan import (
    TriggerScanRequest,
    ScanResponse,
    ScanQueryResultResponse,
    ScanWithResultsResponse,
)

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
    "/client/{client_id}/latest",
    response_model=ScanWithResultsResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_scan(client_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id)
        .order_by(Scan.triggered_at.desc())
        .first()
    )
    if not scan:
        return None

    if scan.status != "completed":
        return ScanWithResultsResponse(
            id=scan.id,
            client_id=scan.client_id,
            platform=scan.platform,
            status=scan.status,
            triggered_at=scan.triggered_at,
            completed_at=scan.completed_at,
            results=[],
        )

    rows = (
        db.query(ScanQueryResult, Competitor.name.label("competitor_name"))
        .outerjoin(Competitor, ScanQueryResult.competitor_id == Competitor.id)
        .filter(ScanQueryResult.scan_id == scan.id)
        .all()
    )
    results = [
        ScanQueryResultResponse(
            id=row.ScanQueryResult.id,
            scan_id=row.ScanQueryResult.scan_id,
            competitor_id=row.ScanQueryResult.competitor_id,
            competitor_name=row.competitor_name,
            category=row.ScanQueryResult.category,
            query_text=row.ScanQueryResult.query_text,
            response_text=row.ScanQueryResult.response_text,
            brand_detected=row.ScanQueryResult.brand_detected,
            created_at=row.ScanQueryResult.created_at,
        )
        for row in rows
    ]
    return ScanWithResultsResponse(
        id=scan.id,
        client_id=scan.client_id,
        platform=scan.platform,
        status=scan.status,
        triggered_at=scan.triggered_at,
        completed_at=scan.completed_at,
        results=results,
    )


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


@router.post(
    "/{scan_id}/results/{result_id}/flag-hallucination",
    dependencies=[Depends(require_api_key)],
)
def flag_hallucination_result(
    scan_id: uuid.UUID,
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    from app.services.alert_service import flag_hallucination
    try:
        flag_hallucination(result_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"flagged": True, "result_id": str(result_id)}
```

- [ ] **Step 3: Run full test suite — no regressions**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/scan.py backend/app/api/v1/scans.py
git commit -m "feat: add scan results endpoint and flag-hallucination endpoint"
```

---

## Task 4: Integrate Alerts into scan_service

**Files:**
- Modify: `backend/app/services/scan_service.py:78-105`

- [ ] **Step 1: Capture prev_geo_score before saving new score**

Open `backend/app/services/scan_service.py`. Find the block that starts with `# Compute and persist GEO score` (around line 78). Replace from that comment through the final `db.commit()` (line ~105) with this:

```python
        # Compute and persist GEO score
        all_results = (
            db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scan.id).all()
        )
        ai_citability = compute_ai_citability(all_results)
        overall = compute_geo_score(client, ai_citability)

        prev_geo_score = (
            db.query(GeoScore)
            .filter(GeoScore.client_id == client.id)
            .order_by(GeoScore.computed_at.desc())
            .first()
        )

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

        db.add(ActivityLog(
            client_id=client.id,
            event_type="scan_completed",
            note=f"Scan completed. AI Citability: {ai_citability:.1f}. Overall GEO score: {overall:.1f}.",
        ))

        scan.status = "completed"
        scan.completed_at = datetime.utcnow()
        db.commit()
        logger.info("scan_completed", scan_id=str(scan_id), overall_score=overall)

        # Alert checks — failures must not corrupt scan state
        try:
            from app.services.alert_service import check_score_drop_alert
            check_score_drop_alert(client, geo_score, prev_geo_score, db)
        except Exception as exc:
            logger.error("score_drop_alert_failed", scan_id=str(scan_id), error=str(exc))

        try:
            from app.services.alert_service import check_competitor_overtake_alert
            check_competitor_overtake_alert(client, scan.id, db)
        except Exception as exc:
            logger.error("competitor_overtake_alert_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 2: Run full test suite — no regressions**

```bash
cd backend
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scan_service.py
git commit -m "feat: integrate score drop and competitor overtake alerts into scan_service"
```

---

## Task 5: Frontend Types + API Functions

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add Scan and ScanQueryResult types**

Open `frontend/src/types/index.ts`. Append at the end of the file:

```typescript
export interface ScanQueryResult {
  id: string
  scan_id: string
  competitor_id: string | null
  competitor_name: string | null
  category: string
  query_text: string
  response_text: string | null
  brand_detected: boolean
  created_at: string
}

export interface Scan {
  id: string
  client_id: string
  platform: string
  status: "pending" | "running" | "completed" | "failed"
  triggered_at: string
  completed_at: string | null
  results: ScanQueryResult[]
}
```

- [ ] **Step 2: Add scan API functions to api.ts**

Open `frontend/src/lib/api.ts`. Find the import line and add `Scan` to the type imports:

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry, Report, Scan } from "@/types"
```

Then append these three functions at the end of the file:

```typescript
// ── Scans ─────────────────────────────────────────────────────────────────────

export function getLatestScan(clientId: string): Promise<Scan | null> {
  return apiFetch<Scan | null>(`/api/v1/scans/client/${clientId}/latest`)
}

export function triggerScan(clientId: string): Promise<{ id: string; status: string }> {
  return apiFetch<{ id: string; status: string }>("/api/v1/scans", {
    method: "POST",
    body: JSON.stringify({ client_id: clientId }),
  })
}

export function flagHallucination(
  scanId: string,
  resultId: string,
): Promise<{ flagged: boolean; result_id: string }> {
  return apiFetch<{ flagged: boolean; result_id: string }>(
    `/api/v1/scans/${scanId}/results/${resultId}/flag-hallucination`,
    { method: "POST" },
  )
}
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
git commit -m "feat: add Scan and ScanQueryResult types and scan API functions"
```

---

## Task 6: Scan Page Frontend

**Files:**
- Create: `frontend/src/app/clients/[id]/scan/actions.ts`
- Create: `frontend/src/app/clients/[id]/scan/ScanClient.tsx`
- Modify: `frontend/src/app/clients/[id]/scan/page.tsx`

- [ ] **Step 1: Create actions.ts**

Create `frontend/src/app/clients/[id]/scan/actions.ts`:

```typescript
"use server"

import { triggerScan, flagHallucination, getLatestScan } from "@/lib/api"
import { revalidatePath } from "next/cache"
import type { Scan } from "@/types"

export async function triggerScanAction(clientId: string): Promise<Scan | null> {
  await triggerScan(clientId)
  revalidatePath(`/clients/${clientId}/scan`)
  revalidatePath(`/clients/${clientId}`)
  try {
    return await getLatestScan(clientId)
  } catch {
    return null
  }
}

export async function flagHallucinationAction(
  scanId: string,
  resultId: string,
  clientId: string,
): Promise<void> {
  await flagHallucination(scanId, resultId)
  revalidatePath(`/clients/${clientId}/activity`)
}

export async function refreshScanAction(clientId: string): Promise<Scan | null> {
  try {
    return await getLatestScan(clientId)
  } catch {
    return null
  }
}
```

- [ ] **Step 2: Create ScanClient.tsx**

Create `frontend/src/app/clients/[id]/scan/ScanClient.tsx`:

```typescript
"use client"

import { useState, useEffect, useTransition } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, Play, CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import type { Scan, ScanQueryResult } from "@/types"
import { triggerScanAction, flagHallucinationAction, refreshScanAction } from "./actions"

interface Props {
  clientId: string
  clientName: string
  initialScan: Scan | null
}

const CATEGORY_LABELS: Record<string, string> = {
  brand: "Brand",
  comparison: "Comparison",
  recommendation: "Recommendation",
  local: "Local",
}

export function ScanClient({ clientId, clientName, initialScan }: Props) {
  const [scan, setScan] = useState<Scan | null>(initialScan)
  const [isPending, startTransition] = useTransition()
  const [flaggingId, setFlaggingId] = useState<string | null>(null)
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(new Set())

  const isActive = scan?.status === "running" || scan?.status === "pending"

  useEffect(() => {
    if (!isActive) return
    const interval = setInterval(async () => {
      const updated = await refreshScanAction(clientId)
      if (updated) setScan(updated)
    }, 3000)
    return () => clearInterval(interval)
  }, [isActive, clientId])

  function handleTrigger() {
    startTransition(async () => {
      const newScan = await triggerScanAction(clientId)
      if (newScan) setScan(newScan)
    })
  }

  function handleFlag(resultId: string) {
    if (!scan) return
    setFlaggingId(resultId)
    startTransition(async () => {
      await flagHallucinationAction(scan.id, resultId, clientId)
      setFlaggingId(null)
      setFlaggedIds((prev) => new Set([...prev, resultId]))
    })
  }

  const clientResults = scan?.results.filter((r) => r.competitor_id === null) ?? []
  const competitorGroups = groupByCompetitor(
    scan?.results.filter((r) => r.competitor_id !== null) ?? [],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Scan &amp; Visibility</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            How AI models respond to queries about {clientName}.
          </p>
        </div>
        <Button size="sm" onClick={handleTrigger} disabled={isPending || isActive}>
          {isActive ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Play className="h-4 w-4 mr-2" />
          )}
          {isActive ? "Scan running…" : "Run New Scan"}
        </Button>
      </div>

      {!scan && (
        <div className="rounded-lg border border-dashed p-14 text-center text-muted-foreground">
          <p className="font-medium">No scans yet</p>
          <p className="text-sm mt-1">
            Click &ldquo;Run New Scan&rdquo; to trigger the first scan.
          </p>
        </div>
      )}

      {scan?.status === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          The last scan failed. Trigger a new scan to retry.
        </div>
      )}

      {isActive && (
        <div className="rounded-lg border bg-muted/30 p-8 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm font-medium">Scan in progress</p>
          <p className="text-sm text-muted-foreground mt-1">
            Querying Gemini across {clientResults.length > 0 ? clientResults.length : "8"} topics.
            This takes about 30 seconds.
          </p>
        </div>
      )}

      {scan?.status === "completed" && (
        <div className="space-y-6">
          <p className="text-xs text-muted-foreground">
            Completed {formatDate(scan.completed_at!)} &middot; Platform:{" "}
            {scan.platform}
          </p>

          <section>
            <h3 className="text-sm font-semibold mb-3">
              Your Brand — {clientResults.length} queries
            </h3>
            <ResultsTable
              results={clientResults}
              flaggingId={flaggingId}
              flaggedIds={flaggedIds}
              onFlag={handleFlag}
            />
          </section>

          {competitorGroups.map(({ competitorName, results }) => (
            <section key={competitorName}>
              <h3 className="text-sm font-semibold mb-3">
                Competitor: {competitorName} — {results.length} queries
              </h3>
              <ResultsTable
                results={results}
                flaggingId={flaggingId}
                flaggedIds={flaggedIds}
                onFlag={handleFlag}
              />
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function ResultsTable({
  results,
  flaggingId,
  flaggedIds,
  onFlag,
}: {
  results: ScanQueryResult[]
  flaggingId: string | null
  flaggedIds: Set<string>
  onFlag: (id: string) => void
}) {
  return (
    <div className="rounded-lg border overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/30">
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground w-28">
              Category
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">
              Query
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground w-40">
              Status
            </th>
            <th className="px-4 py-2.5 text-right text-xs font-medium text-muted-foreground w-24">
              Flag
            </th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => (
            <tr
              key={r.id}
              className={`${i < results.length - 1 ? "border-b" : ""} hover:bg-muted/20 transition-colors`}
            >
              <td className="px-4 py-3">
                <Badge variant="outline" className="text-xs font-normal">
                  {CATEGORY_LABELS[r.category] ?? r.category}
                </Badge>
              </td>
              <td className="px-4 py-3 text-muted-foreground text-sm">{r.query_text}</td>
              <td className="px-4 py-3">
                {r.brand_detected ? (
                  <span className="flex items-center gap-1.5 text-green-600 text-sm">
                    <CheckCircle className="h-3.5 w-3.5 shrink-0" />
                    Seen by AI
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-muted-foreground text-sm">
                    <XCircle className="h-3.5 w-3.5 shrink-0" />
                    Not yet seen by AI
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                {flaggedIds.has(r.id) ? (
                  <span className="text-xs text-muted-foreground">Flagged</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                    onClick={() => onFlag(r.id)}
                    disabled={flaggingId === r.id}
                  >
                    {flaggingId === r.id ? (
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : (
                      <AlertTriangle className="h-3 w-3 mr-1" />
                    )}
                    Flag
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function groupByCompetitor(results: ScanQueryResult[]) {
  const groups = new Map<string, { competitorName: string; results: ScanQueryResult[] }>()
  for (const r of results) {
    const key = r.competitor_id!
    if (!groups.has(key)) {
      groups.set(key, { competitorName: r.competitor_name ?? key, results: [] })
    }
    groups.get(key)!.results.push(r)
  }
  return [...groups.values()]
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
```

- [ ] **Step 3: Rebuild page.tsx**

Replace the full contents of `frontend/src/app/clients/[id]/scan/page.tsx`:

```typescript
import { getClient, getLatestScan } from "@/lib/api"
import { ScanClient } from "./ScanClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ScanPage({ params }: Props) {
  const { id } = await params
  let clientName = "this client"
  let initialScan = null

  try {
    const [client, scan] = await Promise.all([getClient(id), getLatestScan(id)])
    clientName = client.name
    initialScan = scan
  } catch {
    // backend down — show empty state
  }

  return <ScanClient clientId={id} clientName={clientName} initialScan={initialScan} />
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
git add "frontend/src/app/clients/[id]/scan/actions.ts" \
        "frontend/src/app/clients/[id]/scan/ScanClient.tsx" \
        "frontend/src/app/clients/[id]/scan/page.tsx"
git commit -m "feat: build scan page with query results table and flag hallucination button"
```

---

## Task 7: Activity Log UI Update

**Files:**
- Modify: `frontend/src/app/clients/[id]/activity/page.tsx`

- [ ] **Step 1: Add Bell and AlertTriangle to lucide-react import**

Open `frontend/src/app/clients/[id]/activity/page.tsx`. Find the import:

```typescript
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail, FileText } from "lucide-react"
```

Replace with:

```typescript
import { Activity, CheckCircle, XCircle, Wrench, ShieldCheck, UserPlus, Mail, FileText, Bell, AlertTriangle } from "lucide-react"
```

- [ ] **Step 2: Add alert_sent and hallucination_flagged to EVENT_LABELS**

Find the `EVENT_LABELS` object:

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

Replace with:

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
  alert_sent: "Alert sent",
  hallucination_flagged: "Hallucination flagged",
}
```

- [ ] **Step 3: Add alert_sent and hallucination_flagged cases to EventIcon**

Find the `EventIcon` function. Add two cases before `default:`:

```typescript
    case "alert_sent":
      return <Bell className={`${cls} text-red-500`} />
    case "hallucination_flagged":
      return <AlertTriangle className={`${cls} text-amber-500`} />
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
git commit -m "feat: add alert_sent and hallucination_flagged to activity log UI"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Score drop alert fires when overall score crosses below threshold | Task 2 (`check_score_drop_alert`, `was_above and now_below`) |
| Fires once per crossing — not on every scan while below | Task 2 (`was_above` condition — prev must be ≥ threshold) |
| Default threshold 35, configurable per client | Task 2 (`client.score_drop_threshold` — set in settings) |
| Competitor overtake alert fires after scan if competitor exceeds client | Task 2 (`check_competitor_overtake_alert`) |
| Email shows which competitor and score delta | Task 2 (`_build_overtake_email` includes name + delta) |
| Hallucination flag — manual from scan results view | Tasks 3 + 6 (endpoint + Flag button in ScanClient) |
| Hallucination flag creates activity_log + sends alert email | Task 2 (`flag_hallucination` logs `hallucination_flagged` + sends email) |
| Alert email includes query text, AI response, brand name | Task 2 (`_build_hallucination_email`) |
| All alerts sent to contact@seenby.my | Task 1 (`ALERTS_EMAIL` constant) + Task 2 |
| All alerts create activity_log entry | Task 2 (all three functions call `db.add(ActivityLog(...))`) |
| Alerts don't corrupt scan on failure | Task 4 (try/except wrapping each alert call in scan_service) |
| Scan page shows results with "Seen by AI" / "Not yet seen by AI" | Task 6 (`ScanClient.tsx`) |
| Flag button triggers hallucination flag | Task 6 (`handleFlag` → `flagHallucinationAction`) |
| Alert events visible in activity log | Task 7 (`alert_sent`, `hallucination_flagged` labels + icons) |
| Competitor overtake check runs in scan_service post-completion | Task 4 |
| Score drop check runs in scan_service post-completion | Task 4 |
| Prev geo score captured before new score is committed | Task 4 (query before `db.add(geo_score)`) |

### Placeholder Scan

No TBD / TODO / "implement later" found.

### Type Consistency

- `check_score_drop_alert(client, current_geo_score, prev_geo_score, db)` — called in scan_service with `(client, geo_score, prev_geo_score, db)` where `prev_geo_score: GeoScore | None` ✓
- `check_competitor_overtake_alert(client, scan.id, db)` — `scan.id` is `uuid.UUID` matching parameter type ✓
- `flag_hallucination(result_id, db)` — called from API with `result_id: uuid.UUID` ✓
- `ScanQueryResultResponse` fields used identically in `get_latest_scan` endpoint build loop ✓
- `ScanWithResultsResponse.results: list[ScanQueryResultResponse]` — populated in endpoint ✓
- Frontend `Scan.results: ScanQueryResult[]` matches backend `ScanWithResultsResponse.results` ✓
- `flagHallucination(scanId, resultId)` in `api.ts` matches `POST /scans/{scan_id}/results/{result_id}/flag-hallucination` ✓
- `refreshScanAction` returns `Scan | null` matching `useState<Scan | null>` ✓

### Verification Plan (from spec §8)

To verify manually after implementation:
1. In Supabase, find a client with ≥2 completed scans. Edit the most recent `geo_scores` row so `overall_score` is just below the client's `score_drop_threshold`. Trigger a new scan. Confirm alert email received at `contact@seenby.my`.
2. Add a competitor and ensure their queries will out-score the client (edit their `scan_query_results.brand_detected = true`). Trigger a new scan. Confirm competitor overtake email received.
3. Navigate to `/clients/[id]/scan`. After a completed scan, click "Flag" on any result row. Confirm `hallucination_flagged` entry appears in activity log and email received at `contact@seenby.my`.
