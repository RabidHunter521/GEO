"""Deterministic client-period summary (Phase 1, Task 4).

This lives on the PUBLIC client view (/view/{token}), which has stricter
rules than the admin Command Center: only WorkLogEntry.status == "published"
rows are ever client-visible, only RemediationItem rows of a client-safe
item_type ("hallucination" | "content_gap" — never "misinformation") ever
reach this surface, and proof-card excerpts are already-redacted client-safe
strings. Every returned sentence must be built from a stored value — no LLM
call, no free text — and each list is capped at 3 items.
"""
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import desc

from app.core.constants import PLATFORM_LABELS, SCORE_DISPLAY_LABEL
from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.geo_score import GeoScore
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.work_log_entry import WorkLogEntry
from app.schemas.client_view import ClientViewProofCard
from app.services.client_period_summary_service import build_client_period_summary
from app.services.proof_card_service import select_proof_cards


# --- fixtures ----------------------------------------------------------------

def _client(db, **kwargs) -> Client:
    c = Client(
        name=kwargs.pop("name", "Acme Dental"),
        website="https://acme.example",
        industry="Dental",
        **kwargs,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _score(db, client_id, *, overall: float, days_ago: int) -> GeoScore:
    when = utcnow() - timedelta(days=days_ago)
    scan = Scan(client_id=client_id, status="completed", triggered_at=when, completed_at=when)
    db.add(scan)
    db.flush()
    g = GeoScore(
        client_id=client_id, scan_id=scan.id, overall_score=overall,
        ai_citability=overall, brand_authority=overall, content_quality=overall,
        technical_foundations=overall, structured_data=overall, computed_at=when,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return scan, g


def _seeded_client(db) -> Client:
    """One client: two scores, a win + a loss proof card on the latest scan,
    one reviewed (flagged) risk, one in-progress item, one open action, and
    one published work-log entry."""
    client = _client(db)

    _score(db, client.id, overall=52.0, days_ago=14)
    latest_scan, _ = _score(db, client.id, overall=60.0, days_ago=0)

    rival = Competitor(client_id=client.id, name="RivalCo", website="https://rivalco.example")
    db.add(rival)
    db.flush()

    # Win: brand named directly.
    db.add(ScanQueryResult(
        scan_id=latest_scan.id, platform="chatgpt", competitor_id=None,
        category="recommendation", query_text="best dental clinic in KL",
        response_text="Acme Dental is the top recommended dental clinic for families in the city.",
        brand_detected=True, hallucination_flagged=False,
    ))
    # Loss: competitor named, brand absent.
    db.add(ScanQueryResult(
        scan_id=latest_scan.id, platform="perplexity", competitor_id=None,
        category="local", query_text="best dentist near me",
        response_text="RivalCo is a popular choice for dental checkups in the area.",
        brand_detected=False, hallucination_flagged=False,
    ))

    # One reviewed risk — tracked and flagged, not yet corrected.
    db.add(RemediationItem(
        client_id=client.id, item_type="hallucination", platform="gemini",
        label="Does Acme Dental offer braces?", status="flagged",
    ))
    # One item actively being worked on.
    db.add(RemediationItem(
        client_id=client.id, item_type="content_gap", platform="claude",
        label="best orthodontist in KL", detail="RivalCo, OtherCo", status="in_progress",
    ))

    # One open action.
    db.add(ActionRecommendation(
        client_id=client.id, action_text="Publish a page about your braces service.",
        dimension="content_quality", estimated_impact=4.0, priority="medium", status="open",
    ))

    # One published work item, with an internal-looking source_ref that must
    # never surface.
    db.add(WorkLogEntry(
        client_id=client.id, category="content",
        description="Published a new FAQ page answering common patient questions.",
        source="auto", source_ref="toolkit_generated:deadbeef",
        status="published", entry_date=date.today(), published_at=utcnow(),
    ))

    db.commit()
    return client


# --- caller-supplied inputs ---------------------------------------------------
# build_client_period_summary no longer re-derives `history` or `proof_cards`
# itself (Task 4 review, I4) — the caller (client_view.get_overview) computes
# both once and passes them in. These helpers mirror that computation exactly
# (including client_view._client_proof_cards's ordering) so tests exercise the
# same shape the route actually passes.


def _history(db, client_id) -> list[GeoScore]:
    return (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
        .all()
    )


def _proof_cards(db, client) -> list[ClientViewProofCard]:
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .first()
    )
    if not latest_scan:
        return []
    scan_results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(False),
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )
    competitor_names = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    return [
        ClientViewProofCard(
            kind=pc.kind,
            platform_label=PLATFORM_LABELS.get(pc.platform, pc.platform.title()),
            category=pc.category,
            excerpt=pc.excerpt,
        )
        for pc in select_proof_cards(scan_results, client.name, competitor_names)
    ]


def _build_summary(db, client):
    return build_client_period_summary(client, db, _history(db, client.id), _proof_cards(db, client))


# --- contract assertions -----------------------------------------------------

def test_build_client_period_summary_reads_stored_evidence(db):
    client = _seeded_client(db)

    summary = _build_summary(db, client)

    assert SCORE_DISPLAY_LABEL in summary.headline
    assert "60.0" in summary.headline

    joined_wins = " ".join(summary.wins)
    assert "Published a new FAQ page answering common patient questions." in joined_wins
    assert "top recommended dental clinic" in joined_wins

    joined_risks = " ".join(summary.risks)
    assert "Does Acme Dental offer braces?" in joined_risks

    joined_underway = " ".join(summary.work_underway)
    assert "best orthodontist in KL" in joined_underway

    joined_actions = " ".join(summary.next_actions)
    assert "Publish a page about your braces service." in joined_actions


def test_summary_never_carries_raw_response_text_or_internal_keys(db):
    """The full raw response_text and any internal id/event-key must never
    appear verbatim; the proof-card loss excerpt redacts the competitor name.

    Note: RemediationItem.detail (competitor names for a content_gap item) is
    NOT expected to be redacted here — it is already an established
    client-safe field surfaced verbatim on /progress
    (ClientViewProgressItem.detail), by design: naming which competitor is
    winning a given query is the point of that remediation item."""
    client = _seeded_client(db)

    summary = _build_summary(db, client)

    everything = " ".join(
        [summary.headline, *summary.wins, *summary.risks,
         *summary.work_underway, *summary.next_actions]
    )
    assert "toolkit_generated:deadbeef" not in everything
    # The full raw loss response_text never appears verbatim.
    assert "RivalCo is a popular choice for dental checkups in the area." not in everything
    # The loss proof-card sentence specifically redacts the competitor name.
    loss_sentences = [r for r in summary.risks if "named a competitor instead of you" in r]
    assert loss_sentences and "RivalCo" not in loss_sentences[0]


def test_unpublished_work_log_entries_never_appear(db):
    client = _seeded_client(db)
    db.add(WorkLogEntry(
        client_id=client.id, category="visibility",
        description="SECRET_SUGGESTED_ONLY_TEXT not yet reviewed by admin",
        source="auto", status="suggested", entry_date=date.today(),
    ))
    db.add(WorkLogEntry(
        client_id=client.id, category="visibility",
        description="SECRET_DISMISSED_TEXT admin rejected this",
        source="auto", status="dismissed", entry_date=date.today(),
    ))
    db.commit()

    summary = _build_summary(db, client)

    everything = " ".join(
        [summary.headline, *summary.wins, *summary.risks,
         *summary.work_underway, *summary.next_actions]
    )
    assert "SECRET_SUGGESTED_ONLY_TEXT" not in everything
    assert "SECRET_DISMISSED_TEXT" not in everything


def test_misinformation_remediation_items_never_appear(db):
    """Misinformation findings are compliance-workflow-only (spec 8 §4) —
    only "hallucination" and "content_gap" remediation types ever reach a
    client surface.

    status="flagged" deliberately — that's the status a real misinformation
    item is created with (misinformation_service.py) and the one status that
    WOULD render a sentence in _remediation_sentences if the item_type
    allowlist there were ever removed. A status not in REMEDIATION_STATUSES
    (e.g. the old "confirmed") would make this test pass for the wrong
    reason: it wouldn't hit either branch in _remediation_sentences even
    without the allowlist, so the allowlist itself would go unexercised."""
    client = _seeded_client(db)
    db.add(RemediationItem(
        client_id=client.id, item_type="misinformation", platform="chatgpt",
        label="CONFIDENTIAL_COMPLIANCE_FINDING", status="flagged",
    ))
    db.commit()

    summary = _build_summary(db, client)

    everything = " ".join(
        [summary.headline, *summary.wins, *summary.risks, *summary.work_underway]
    )
    assert "CONFIDENTIAL_COMPLIANCE_FINDING" not in everything


def test_lists_are_capped_at_three(db):
    client = _client(db)
    for i in range(5):
        db.add(RemediationItem(
            client_id=client.id, item_type="hallucination", platform="chatgpt",
            label=f"question {i}", status="flagged",
        ))
        db.add(RemediationItem(
            client_id=client.id, item_type="content_gap", platform="gemini",
            label=f"underway {i}", status="in_progress",
        ))
        db.add(ActionRecommendation(
            client_id=client.id, action_text=f"Action {i}",
            dimension="content_quality", estimated_impact=float(i), status="open",
        ))
        db.add(WorkLogEntry(
            client_id=client.id, category="content", description=f"Delivered item {i}",
            source="manual", status="published", entry_date=date.today(), published_at=utcnow(),
        ))
    db.commit()

    summary = _build_summary(db, client)

    assert len(summary.wins) <= 3
    assert len(summary.risks) <= 3
    assert len(summary.work_underway) <= 3
    assert len(summary.next_actions) <= 3


def test_headline_reports_baseline_with_no_previous_score(db):
    client = _client(db)
    _score(db, client.id, overall=60.0, days_ago=0)

    summary = _build_summary(db, client)

    assert SCORE_DISPLAY_LABEL in summary.headline
    assert "60.0" in summary.headline


def test_headline_when_no_score_at_all(db):
    client = _client(db)

    summary = _build_summary(db, client)

    assert summary.headline
    assert summary.wins == []
    assert summary.risks == []
    assert summary.work_underway == []
    assert summary.next_actions == []


def test_headline_reports_a_decline(db):
    client = _client(db)
    _score(db, client.id, overall=60.0, days_ago=14)
    _score(db, client.id, overall=55.0, days_ago=0)

    summary = _build_summary(db, client)

    assert "5.0" in summary.headline
    assert "55.0" in summary.headline


def test_headline_says_this_period_within_the_30_day_window(db):
    """Two scores 14 days apart genuinely fall within the 30-day window this
    surface treats as "this period" elsewhere (improvements_last_30d, the
    monthly report cadence) — the headline may say so."""
    client = _client(db)
    _score(db, client.id, overall=52.0, days_ago=14)
    _score(db, client.id, overall=60.0, days_ago=0)

    summary = _build_summary(db, client)

    assert "this period" in summary.headline.lower()


def test_headline_does_not_claim_a_period_when_scans_are_far_apart(db):
    """I3: a client whose last two scans are five months apart must not read
    "...this period" — that asserts a uniform window none of the underlying
    data actually supports (work-log wins are a real 30-day window;
    remediation risks/work-underway and next_actions are all-time). The
    headline must instead name the actual comparison date."""
    client = _client(db)
    _score(db, client.id, overall=52.0, days_ago=150)
    _score(db, client.id, overall=60.0, days_ago=0)

    summary = _build_summary(db, client)

    assert "this period" not in summary.headline.lower()
    assert "8.0" in summary.headline
    assert "60.0" in summary.headline
    # Every sentence must be true of the data it's built from: the headline
    # must name the actual prior scan date it's comparing against.
    previous_score = _history(db, client.id)[1]
    assert f"{previous_score.computed_at:%B %d, %Y}" in summary.headline


def test_never_calls_an_llm(db):
    client = _seeded_client(db)

    with patch(
        "app.services.claude_client.anthropic_client",
        side_effect=AssertionError("period summary must not call Claude"),
    ):
        summary = _build_summary(db, client)

    assert summary.headline


def test_build_writes_nothing(db):
    client = _seeded_client(db)

    _build_summary(db, client)

    assert list(db.new) == []
    assert list(db.dirty) == []
    assert list(db.deleted) == []


def test_prospect_gets_only_the_headline(db):
    """Prospects get a deliberately limited view everywhere else on this
    surface (proof_cards always [], /progress and /actions 404) — this
    summary must not become the one path that leaks retainer-work evidence
    to a not-yet-paying lead."""
    client = _client(db, is_prospect=True)
    _score(db, client.id, overall=60.0, days_ago=0)
    db.add(RemediationItem(
        client_id=client.id, item_type="hallucination", platform="chatgpt",
        label="PROSPECT_SHOULD_NOT_SEE_THIS", status="flagged",
    ))
    db.add(ActionRecommendation(
        client_id=client.id, action_text="PROSPECT_SHOULD_NOT_SEE_ACTION",
        dimension="content_quality", estimated_impact=4.0, status="open",
    ))
    db.add(WorkLogEntry(
        client_id=client.id, category="content", description="PROSPECT_SHOULD_NOT_SEE_WORK",
        source="manual", status="published", entry_date=date.today(), published_at=utcnow(),
    ))
    db.commit()

    summary = _build_summary(db, client)

    assert summary.headline
    assert summary.wins == []
    assert summary.risks == []
    assert summary.work_underway == []
    assert summary.next_actions == []


def test_another_clients_rows_are_never_counted(db):
    client = _seeded_client(db)
    other = _client(db, name="Other Co")
    db.add(RemediationItem(
        client_id=other.id, item_type="hallucination", platform="chatgpt",
        label="not mine", status="flagged",
    ))
    db.add(WorkLogEntry(
        client_id=other.id, category="content", description="NOT_MINE_WORK",
        source="manual", status="published", entry_date=date.today(), published_at=utcnow(),
    ))
    db.commit()

    summary = _build_summary(db, client)

    everything = " ".join([*summary.wins, *summary.risks])
    assert "not mine" not in everything
    assert "NOT_MINE_WORK" not in everything
