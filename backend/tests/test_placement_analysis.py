"""Placement engine Task 4: deterministic page analysis + admin API."""
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.placement_target import PlacementTarget
from app.services import placement_service as ps
from app.services.url_safety import SafeResponse, UnsafeUrlError
from tests.auth_helpers import owner_headers

FIXTURES = Path(__file__).parent / "fixtures" / "placements"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _comps():
    return [("c-rival", "Rival Dental"), ("c-other", "Other Rival Clinic")]


# ── pure parser ─────────────────────────────────────────────────────────────

def test_listicle_structure_and_competitor_positions():
    a = ps.analyze_page(_html("listicle.html"), "https://klguide.example/best-dentists", _comps())

    assert a["is_listicle"] is True
    assert a["entries_count"] == 5
    assert a["entries"][:2] == ["Rival Dental", "Smile Studio Bangsar"]
    assert a["competitors_listed"] == [
        {"competitor_id": "c-rival", "name": "Rival Dental", "position": 1},
        {"competitor_id": "c-other", "name": "Other Rival Clinic", "position": 5},
    ]
    assert a["other_businesses_listed"] == 3
    assert a["author"] == "Aisyah Rahman"
    assert a["site_name"] == "KL Guide"
    assert a["published"] == "2026-03-01"
    assert a["modified"] == "2026-08-15"


def test_listicle_contact_routes():
    a = ps.analyze_page(_html("listicle.html"), "https://klguide.example/best-dentists", _comps())

    assert a["contact"]["emails"] == ["editor@klguide.example"]
    assert a["contact"]["contact_pages"] == ["https://klguide.example/contact-us"]
    assert a["contact"]["submission_links"] == ["https://klguide.example/suggest-a-business"]


def test_directory_submission_links_are_absolute():
    a = ps.analyze_page(_html("directory.html"), "https://www.yellowpages.my/dentists/kl", _comps())

    assert a["is_listicle"] is False
    assert a["contact"]["submission_links"] == [
        "https://www.yellowpages.my/add-your-business",
        "https://www.yellowpages.my/claim-listing",
    ]
    assert [c["name"] for c in a["competitors_listed"]] == ["Rival Dental"]
    assert a["competitors_listed"][0]["position"] is None  # not a ranked list


def test_page_without_contact_routes():
    a = ps.analyze_page(_html("plain.html"), "https://blog.example/choose", _comps())

    assert a["is_listicle"] is False
    assert a["entries_count"] == 0
    assert a["contact"] == {"emails": [], "contact_pages": [], "submission_links": []}
    assert a["competitors_listed"] == []


# ── analyze_target: fetching, fail-open, contact-page follow-up ─────────────

def _target(db, url="https://klguide.example/best-dentists"):
    client = Client(id=uuid.uuid4(), name="Acme Dental", website="https://acme.com", industry="dentist")
    db.add(client)
    db.add(Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival Dental"))
    t = PlacementTarget(client_id=client.id, url=url, domain="klguide.example", category="listicle",
                        answers_count=2, platforms=["chatgpt"], query_categories=["recommendation"])
    db.add(t)
    db.commit()
    return t


def _ok(html, url):
    return SafeResponse(200, html, {"content-type": "text/html"}, url=url)


def test_analyze_target_stores_analysis_and_rescores(db):
    t = _target(db)
    before = t.priority_score
    with patch.object(ps, "safe_get", return_value=_ok(_html("listicle.html"), t.url)) as get:
        ps.analyze_target(t, db)
    assert get.call_count == 1  # the page already showed an email: no contact-page fetch

    db.refresh(t)
    assert t.page_analysis["fetch_status"] == "ok"
    assert t.page_analysis["is_listicle"] is True
    assert t.other_businesses_listed == 4  # 5 entries, 1 tracked competitor
    assert t.analyzed_at is not None
    assert t.priority_score > before


def test_analyze_target_follows_the_contact_page_once_when_no_email_on_the_page(db):
    t = _target(db)
    page = _html("listicle.html").replace(
        '<a href="mailto:editor@klguide.example">Email the editor</a>', "")
    contact = '<html><body><a href="mailto:hello@klguide.example">Write to us</a></body></html>'

    def fake_get(url, **kw):
        return _ok(contact if url.endswith("/contact-us") else page, url)

    with patch.object(ps, "safe_get", side_effect=fake_get) as get:
        ps.analyze_target(t, db)

    assert get.call_count == 2
    assert t.page_analysis["contact"]["emails"] == ["hello@klguide.example"]


def test_contact_page_on_another_domain_is_not_fetched(db):
    t = _target(db)
    page = '<html><body><a href="https://tracker.example/contact">Contact</a></body></html>'
    with patch.object(ps, "safe_get", return_value=_ok(page, t.url)) as get:
        ps.analyze_target(t, db)
    assert get.call_count == 1


@pytest.mark.parametrize("error,status", [(UnsafeUrlError("x"), "blocked"), (RuntimeError("x"), "error")])
def test_analyze_target_fails_open(db, error, status):
    t = _target(db)
    with patch.object(ps, "safe_get", side_effect=error):
        ps.analyze_target(t, db)
    assert t.page_analysis == {"fetch_status": status}
    assert t.analyzed_at is not None


def test_non_html_response_is_an_error(db):
    t = _target(db)
    with patch.object(ps, "safe_get",
                      return_value=SafeResponse(200, "%PDF", {"content-type": "application/pdf"}, url=t.url)):
        ps.analyze_target(t, db)
    assert t.page_analysis == {"fetch_status": "error"}


# ── admin API ───────────────────────────────────────────────────────────────

@pytest.fixture
def api(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_routes_require_auth(api, db):
    t = _target(db)
    assert api.get(f"/api/v1/clients/{t.client_id}/placements").status_code == 401


def test_list_is_ranked_and_resolves_competitor_names(api, db):
    t = _target(db)
    rival = db.query(Competitor).filter_by(client_id=t.client_id).one()
    t.competitors_present = [str(rival.id)]
    t.priority_score = 40
    db.add(PlacementTarget(client_id=t.client_id, url="https://low.example/a", domain="low.example",
                           category="social", priority_score=5))
    db.commit()

    r = api.get(f"/api/v1/clients/{t.client_id}/placements", headers=owner_headers())

    assert r.status_code == 200
    body = r.json()
    assert [row["domain"] for row in body] == ["klguide.example", "low.example"]
    assert body[0]["competitors"] == ["Rival Dental"]
    assert "page_analysis" not in body[0]  # list stays light; detail has it


def test_detail_includes_the_proof_question_and_analysis(api, db):
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult

    t = _target(db)
    scan = Scan(client_id=t.client_id, status="completed")
    db.add(scan)
    db.flush()
    sqr = ScanQueryResult(scan_id=scan.id, platform="gemini", category="local",
                          query_text="best dentist near Bangsar", response_text="…", brand_detected=False)
    db.add(sqr)
    db.flush()
    t.representative_result_id = sqr.id
    t.page_analysis = {"fetch_status": "ok", "is_listicle": True}
    db.commit()

    r = api.get(f"/api/v1/clients/{t.client_id}/placements/{t.id}", headers=owner_headers())

    assert r.status_code == 200
    body = r.json()
    assert body["proof_question"] == {"query_text": "best dentist near Bangsar", "platform": "gemini"}
    assert body["page_analysis"]["is_listicle"] is True


def test_other_clients_target_is_404(api, db):
    t = _target(db)
    other = Client(name="Other", website="https://o.com", industry="x")
    db.add(other)
    db.commit()
    r = api.get(f"/api/v1/clients/{other.id}/placements/{t.id}", headers=owner_headers())
    assert r.status_code == 404


def test_analyze_route(api, db):
    t = _target(db)
    with patch.object(ps, "safe_get", return_value=_ok(_html("listicle.html"), t.url)):
        r = api.post(f"/api/v1/clients/{t.client_id}/placements/{t.id}/analyze", headers=owner_headers())
    assert r.status_code == 200
    assert r.json()["page_analysis"]["is_listicle"] is True


def test_dismiss_and_reopen(api, db):
    t = _target(db)
    url = f"/api/v1/clients/{t.client_id}/placements/{t.id}"
    assert api.patch(url, headers=owner_headers(), json={"status": "dismissed"}).json()["status"] == "dismissed"
    assert api.patch(url, headers=owner_headers(), json={"status": "open"}).json()["status"] == "open"


def test_patch_cannot_jump_to_placed_or_verified(api, db):
    t = _target(db)
    url = f"/api/v1/clients/{t.client_id}/placements/{t.id}"
    for status in ("placed", "verified", "pursuing"):
        assert api.patch(url, headers=owner_headers(), json={"status": status}).status_code == 422


def test_a_target_in_delivery_cannot_be_dismissed_by_hand(api, db):
    t = _target(db)
    t.status = "pursuing"
    db.commit()
    r = api.patch(f"/api/v1/clients/{t.client_id}/placements/{t.id}",
                  headers=owner_headers(), json={"status": "dismissed"})
    assert r.status_code == 409
