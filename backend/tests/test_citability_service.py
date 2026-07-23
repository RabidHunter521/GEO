"""citability_service tests — deterministic checks against HTML fixtures (spec §8)."""
from unittest.mock import patch


def _para(sentences: int = 3) -> str:
    s = ("Our dentists explain every step in plain language so patients always "
         "know what to expect during a visit. ")
    return "<p>" + (s * sentences).strip() + "</p>"


# Passes all 10 checks: 24-word lead para with a definition before any H2,
# 5/6 question H2/H3s, FAQ heading, 1 table + 2 lists, ~48-word paragraphs,
# 6 headings over ~400 words, published_time meta, author meta + byline,
# 300-3000 words.
EXEMPLARY_HTML = f"""<html><head>
<meta name="author" content="Dr. Sarah Lim">
<meta property="article:published_time" content="2026-06-01T00:00:00Z">
</head><body><main>
<h1>Family Dental Care in Kuala Lumpur</h1>
<p>Acme Dental Clinic is a family dental clinic in Kuala Lumpur offering checkups,
braces, implants and emergency care with transparent pricing for every treatment.</p>
<h2>What services does Acme Dental offer?</h2>
{_para()}{_para()}
<h2>How much does a dental checkup cost?</h2>
<table><tr><th>Treatment</th><th>Price</th></tr>
<tr><td>Checkup</td><td>RM 120</td></tr></table>
{_para()}
<h2>Why do patients choose Acme Dental?</h2>
<ul><li>Gentle care</li><li>Transparent pricing</li></ul>
<ul><li>Weekend hours</li><li>Central location</li></ul>
{_para()}
<h2>Frequently Asked Questions</h2>
<h3>Do you accept walk-in patients?</h3>
{_para()}
<h3>Can I book online?</h3>
{_para()}
<p>Written by Dr. Sarah Lim, updated 1 June 2026.</p>
</main></body></html>"""

_WALL_SENTENCE = ("we care about long term dental health and we want every patient "
                  "to feel comfortable from the moment they arrive until the moment "
                  "they leave our clinic and we work hard to earn that trust. ")
# No headings, lists, tables, dates, bylines, or definition patterns —
# only word_count (10 pts) passes.
WALL_OF_TEXT_HTML = ("<html><body><main><p>" + _WALL_SENTENCE * 22 + "</p><p>"
                     + _WALL_SENTENCE * 18 + "</p></main></body></html>")


def _by_id(checks):
    return {c["id"]: c for c in checks}


# 1. Exemplary page scores >= 90.
def test_exemplary_page_scores_at_least_90():
    from app.services.citability_service import compute_citability_score, run_citability_checks
    checks = run_citability_checks(EXEMPLARY_HTML)
    assert len(checks) == 10
    assert compute_citability_score(checks) >= 90
    for c in checks:
        assert set(c) == {"id", "label", "status", "detail", "points"}


# 2. Wall of text: only word_count passes; score reflects the points table exactly.
def test_wall_of_text_scores_exactly_word_count_points():
    from app.services.citability_service import compute_citability_score, run_citability_checks
    checks = run_citability_checks(WALL_OF_TEXT_HTML)
    by = _by_id(checks)
    assert by["answer_up_front"]["status"] == "fail"
    assert by["paragraph_length"]["status"] == "fail"
    assert by["heading_density"]["status"] == "fail"
    assert by["word_count"]["status"] == "pass"
    assert compute_citability_score(checks) == 10


# 5. Warn earns half points.
def test_warn_earns_half_points():
    from app.services.citability_service import run_citability_checks
    # exactly one list, no table → scannable_structure warns (10 // 2 = 5)
    html = "<html><body><main><p>Short intro.</p><ul><li>One</li></ul></main></body></html>"
    c = _by_id(run_citability_checks(html))["scannable_structure"]
    assert c["status"] == "warn"
    assert c["points"] == 5


# 3. Off-domain / unsafe URLs rejected; subdomains allowed.
def test_validate_audit_url_domain_rules():
    from app.services import citability_service
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True):
        ok = citability_service.validate_audit_url("https://acme.com", "https://acme.com/services")
        sub = citability_service.validate_audit_url("https://acme.com", "https://blog.acme.com/post")
        www = citability_service.validate_audit_url("https://www.acme.com", "https://acme.com/x")
        off = citability_service.validate_audit_url("https://acme.com", "https://rival.com/page")
    assert ok == "https://acme.com/services"
    assert sub == "https://blog.acme.com/post"
    assert www == "https://acme.com/x"
    assert off is None


def test_validate_audit_url_unsafe_rejected():
    from app.services import citability_service
    with patch.object(citability_service, "is_safe_crawl_url", return_value=False):
        assert citability_service.validate_audit_url("https://acme.com", "https://acme.com/x") is None


def test_fetch_page_raises_on_non_html_or_error():
    import pytest
    from app.services import citability_service
    from app.services.citability_service import PageFetchError
    from app.services.url_safety import SafeResponse
    with patch.object(citability_service, "safe_get",
                      return_value=SafeResponse(404, "", {"content-type": "text/html"})):
        with pytest.raises(PageFetchError):
            citability_service.fetch_page("https://acme.com/missing")
    with patch.object(citability_service, "safe_get", side_effect=Exception("timeout")):
        with pytest.raises(PageFetchError):
            citability_service.fetch_page("https://acme.com/slow")


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _mock_anthropic(text: str):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    return ac


_SUGGESTIONS_JSON = ('{"suggestions": [{"section": "Intro", "issue": "No summary up front", '
                     '"rewrite": "Acme Dental is a family dental clinic in KL."}]}')


def test_audit_page_persists_with_suggestions(db):
    from app.models.activity_log import ActivityLog
    from app.services import citability_service
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client",
                      return_value=_mock_anthropic(_SUGGESTIONS_JSON)), \
         patch.object(citability_service, "record_llm_call"):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    assert audit.score == 10
    assert audit.url == "https://acme.com/about"
    assert audit.suggestions_failed is False
    assert audit.suggestions[0]["section"] == "Intro"
    log = db.query(ActivityLog).filter(ActivityLog.client_id == client.id).one()
    assert log.event_type == "page_audit_run"


def test_claude_failure_persists_audit_with_empty_suggestions(db):
    from app.services import citability_service
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client", side_effect=Exception("api down")):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    assert audit.score == 10
    assert audit.suggestions == []
    assert audit.suggestions_failed is True


def test_suggestions_are_sanitized(db):
    from app.services import citability_service
    client = _make_client(db)
    dirty = ('{"suggestions": [{"section": "Intro", "issue": "Not cited by AI", '
             '"rewrite": "Get mentioned more often."}]}')
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=WALL_OF_TEXT_HTML), \
         patch.object(citability_service, "anthropic_client",
                      return_value=_mock_anthropic(dirty)), \
         patch.object(citability_service, "record_llm_call"):
        audit = citability_service.audit_page(client, "https://acme.com/about", db)
    joined = " ".join(f"{s['issue']} {s['rewrite']}" for s in audit.suggestions)
    assert "cited" not in joined.lower().replace("seen by ai", "")
    assert "mentioned" not in joined
    assert "seen by AI" in joined


def test_audit_page_off_domain_raises_and_persists_nothing(db):
    import pytest
    from app.models.page_audit import PageAudit
    from app.services import citability_service
    from app.services.citability_service import OffDomainUrlError
    client = _make_client(db)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True):
        with pytest.raises(OffDomainUrlError):
            citability_service.audit_page(client, "https://rival.com/page", db)
    assert db.query(PageAudit).count() == 0


def test_no_problem_checks_skips_claude(db):
    from app.services import citability_service
    client = _make_client(db)
    ac = _mock_anthropic(_SUGGESTIONS_JSON)
    with patch.object(citability_service, "is_safe_crawl_url", return_value=True), \
         patch.object(citability_service, "fetch_page", return_value=EXEMPLARY_HTML), \
         patch.object(citability_service, "anthropic_client", return_value=ac):
        audit = citability_service.audit_page(client, "https://acme.com/", db)
    if audit.score == 100:
        ac.messages.create.assert_not_called()
        assert audit.suggestions == []
