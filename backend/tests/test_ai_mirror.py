"""Day-one AI Mirror: service rules + admin and client-view endpoints.

Seeds real rows into the in-memory SQLite `db` fixture (conftest.py) — the
mirror reads only what a scan already stored, so no platform calls to mock.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_mirror_service
from app.services.ai_mirror_service import build_ai_mirror, mirror_excerpts

YOU_DENIAL = (
    "Acme Dental does not appear to be a recognized company in my training data. "
    "If you can share more details, I can try to help further."
)
RIVAL_ANSWER = (
    "Smile Studio is a well-regarded dental clinic in Kuala Lumpur offering implants and braces. "
    "Patients often praise Smile Studio for its modern equipment and friendly staff. "
    "It has several branches across the Klang Valley area today. "
    "Smile Studio also offers weekend appointments for working adults."
)


def _client(db, *, is_prospect=False, name="Acme Dental"):
    from app.models.client import Client
    c = Client(
        id=uuid.uuid4(), name=name, website="https://acme.example", industry="Dental",
        share_token=uuid.uuid4().hex, scan_cadence_days=30, is_prospect=is_prospect,
    )
    db.add(c)
    db.flush()
    return c


def _competitor(db, client, name):
    from app.models.competitor import Competitor
    comp = Competitor(id=uuid.uuid4(), client_id=client.id, name=name)
    db.add(comp)
    db.flush()
    return comp


def _scan(db, client, completed_at=datetime(2026, 10, 1, 9)):
    from app.models.scan import Scan
    s = Scan(id=uuid.uuid4(), client_id=client.id, status="completed",
             triggered_at=completed_at - timedelta(minutes=5), completed_at=completed_at)
    db.add(s)
    db.flush()
    return s


_tick = [0]


def _row(db, scan, *, platform="chatgpt", category="brand", query_text, response_text,
         brand_detected, competitor=None, flagged=False):
    from app.models.scan_query_result import ScanQueryResult
    _tick[0] += 1
    r = ScanQueryResult(
        id=uuid.uuid4(), scan_id=scan.id, platform=platform,
        competitor_id=competitor.id if competitor else None, category=category,
        query_text=query_text, response_text=response_text, brand_detected=brand_detected,
        hallucination_flagged=flagged, created_at=datetime(2026, 10, 1) + timedelta(seconds=_tick[0]),
    )
    db.add(r)
    db.flush()
    return r


def _seed(db, *, flag_you=False):
    """Acme isn't recognised by ChatGPT; Smile Studio is, and wins buyer answers."""
    client = _client(db)
    rival = _competitor(db, client, "Smile Studio")
    other = _competitor(db, client, "Bright Teeth")
    scan = _scan(db, client)
    _row(db, scan, query_text="Tell me about Acme Dental", response_text=YOU_DENIAL,
         brand_detected=False, flagged=flag_you)
    _row(db, scan, query_text="What is Acme Dental known for?", response_text="Unknown.",
         brand_detected=False)
    _row(db, scan, query_text="Tell me about Smile Studio", response_text=RIVAL_ANSWER,
         brand_detected=True, competitor=rival)
    _row(db, scan, query_text="Tell me about Bright Teeth",
         response_text="Bright Teeth is a family dental practice in Petaling Jaya with good reviews.",
         brand_detected=True, competitor=other)
    _row(db, scan, category="recommendation", query_text="Best Dental in KL",
         response_text="Top picks include Smile Studio and Bright Teeth for families in the city.",
         brand_detected=False)
    _row(db, scan, category="local", query_text="Top-rated Dental in KL",
         response_text="Smile Studio is the clinic most patients rate highly for cleanings here.",
         brand_detected=False)
    _row(db, scan, category="local", query_text="Affordable Dental in KL",
         response_text="Acme Dental offers some of the most affordable cleanings in the city centre.",
         brand_detected=True)
    _row(db, scan, platform="gemini", query_text="Tell me about Acme Dental",
         response_text="Acme Dental is a dental clinic in Kuala Lumpur that focuses on family care.",
         brand_detected=True)
    _row(db, scan, platform="gemini", query_text="Tell me about Smile Studio",
         response_text=RIVAL_ANSWER, brand_detected=True, competitor=rival)
    return client, rival, scan


# ── service ─────────────────────────────────────────────────────────────────

def test_mirror_pairs_same_question_same_platform_chatgpt_first(db):
    client, rival, scan = _seed(db)
    m = build_ai_mirror(client, db)

    assert m.status == "ready"
    assert m.competitor_name == "Smile Studio"
    assert m.competitor_basis == "buyer_answers"
    assert m.checked_at == scan.completed_at
    assert [p.platform for p in m.platforms] == ["chatgpt", "gemini"]

    chatgpt = m.platforms[0]
    assert chatgpt.same_question is True
    assert chatgpt.you.question == "Tell me about Acme Dental"
    assert chatgpt.competitor.question == "Tell me about Smile Studio"
    assert chatgpt.you.status == "not_seen"
    assert chatgpt.competitor.status == "seen"
    # One denominator for both counts: the client's own buyer questions on ChatGPT.
    assert (chatgpt.buyer_answers_total, chatgpt.buyer_answers_you,
            chatgpt.buyer_answers_competitor) == (3, 1, 2)


def test_mirror_quotes_are_verbatim_sentences_of_the_stored_answer(db):
    client, _, _ = _seed(db)
    chatgpt = build_ai_mirror(client, db).platforms[0]
    assert chatgpt.you.excerpts == [
        "Acme Dental does not appear to be a recognized company in my training data."
    ]
    assert len(chatgpt.competitor.excerpts) == 3
    for quote in chatgpt.competitor.excerpts:
        assert quote in RIVAL_ANSWER


def test_mirror_falls_back_to_first_brand_question_and_says_so(db):
    """Packed clients aren't asked 'Tell me about {brand}'."""
    client = _client(db)
    rival = _competitor(db, client, "Smile Studio")
    scan = _scan(db, client)
    _row(db, scan, query_text="What is Acme Dental?",
         response_text="Acme Dental is a dental clinic in Kuala Lumpur that focuses on family care.",
         brand_detected=True)
    _row(db, scan, query_text="Tell me about Smile Studio", response_text=RIVAL_ANSWER,
         brand_detected=True, competitor=rival)
    p = build_ai_mirror(client, db).platforms[0]
    assert p.same_question is False
    assert p.you.question == "What is Acme Dental?"
    assert p.you.status == "seen"


def test_mirror_picks_most_visible_rival_when_no_buyer_answer_names_one(db):
    client = _client(db)
    quiet = _competitor(db, client, "Alpha Clinic")
    loud = _competitor(db, client, "Zeta Clinic")
    scan = _scan(db, client)
    _row(db, scan, query_text="Tell me about Alpha Clinic", response_text="No idea.",
         brand_detected=False, competitor=quiet)
    _row(db, scan, query_text="Tell me about Zeta Clinic", response_text=RIVAL_ANSWER,
         brand_detected=True, competitor=loud)
    m = build_ai_mirror(client, db)
    assert (m.competitor_name, m.competitor_basis) == ("Zeta Clinic", "visibility")
    # The client side was never asked on this scan: say so, don't invent it.
    assert m.platforms[0].you.status == "no_answer"
    assert m.platforms[0].you.excerpts == []


def test_mirror_states_when_there_is_nothing_to_show(db):
    client = _client(db)
    assert build_ai_mirror(client, db).status == "no_scan"
    _scan(db, client)
    assert build_ai_mirror(client, db).status == "no_competitors"


def test_purged_answer_is_no_answer_not_a_verdict(db):
    client = _client(db)
    rival = _competitor(db, client, "Smile Studio")
    scan = _scan(db, client)
    _row(db, scan, query_text="Tell me about Acme Dental", response_text=None, brand_detected=False)
    _row(db, scan, query_text="Tell me about Smile Studio", response_text=None,
         brand_detected=True, competitor=rival)
    p = build_ai_mirror(client, db).platforms[0]
    assert p.you.status == "no_answer"
    assert p.competitor.status == "seen"
    assert p.competitor.excerpts == []


def test_excerpts_skip_list_rows_and_never_cut_mid_word():
    long = "Smile Studio " + "offers excellent orthodontic treatment " * 12 + "today."
    text = f"1. Smile Studio\n{long}"
    [quote] = mirror_excerpts(text, "Smile Studio")
    assert quote.endswith("…")
    assert len(quote) <= 280
    assert quote[:-1] == long[: len(quote) - 1]
    assert long[len(quote) - 1] == " "  # the cut landed on a word boundary


def test_excerpts_fall_back_to_opening_sentences_when_name_absent():
    assert mirror_excerpts(
        "I'm sorry, I do not have any information on that particular business.", "Acme"
    ) == ["I'm sorry, I do not have any information on that particular business."]


# ── endpoints ───────────────────────────────────────────────────────────────

@pytest.fixture
def http(db):
    from app.core.auth import require_api_key
    from app.core.database import get_db
    from app.api.v1.client_view import _view_rate_limit

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    app.dependency_overrides[_view_rate_limit] = lambda: None
    app.dependency_overrides[require_api_key] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_client_view_mirror_is_whitelisted_and_drops_flagged_answers(db, http):
    client, _, _ = _seed(db, flag_you=True)
    res = http.get(f"/api/v1/view/{client.share_token}/mirror")
    assert res.status_code == 200
    body = res.json()
    assert body["competitor_name"] == "Smile Studio"
    chatgpt = body["platforms"][0]
    assert chatgpt["platform_label"] == "ChatGPT"
    assert "platform" not in chatgpt
    for side in (chatgpt["you"], chatgpt["competitor"]):
        assert "response_text" not in side
        assert "flagged_inaccurate" not in side
    # The flagged "Tell me about" answer is gone; the next brand question is used.
    assert chatgpt["you"]["question"] == "What is Acme Dental known for?"
    assert chatgpt["same_question"] is False
    assert YOU_DENIAL not in res.text


def test_client_view_mirror_is_404_for_prospects(db, http):
    client = _client(db, is_prospect=True)
    assert http.get(f"/api/v1/view/{client.share_token}/mirror").status_code == 404


def test_admin_mirror_keeps_flag_and_full_answer(db, http):
    client, _, _ = _seed(db, flag_you=True)
    res = http.get(f"/api/v1/clients/{client.id}/competitors/mirror")
    assert res.status_code == 200
    chatgpt = res.json()["platforms"][0]
    assert chatgpt["platform"] == "chatgpt"
    assert chatgpt["you"]["flagged_inaccurate"] is True
    assert chatgpt["you"]["response_text"] == YOU_DENIAL
    assert chatgpt["same_question"] is True


def test_client_view_mapping_has_no_admin_fields():
    admin_only = {"response_text", "flagged_inaccurate"}
    side_fields = set(ai_mirror_service.ClientViewMirrorSide.model_fields)
    assert not side_fields & admin_only
