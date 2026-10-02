import uuid
from unittest.mock import patch

from app.models.scan import Scan
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import scan_service
from app.services.platform_clients.base import PlatformResult, SourceCitation
from app.core.constants import GROUNDING_REDIRECT_HOSTS
from app.services.provenance_service import canonical_source_url


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(c)
    db.commit()
    return c


def test_sources_cascade_insert_via_relationship(db):
    c = _client(db)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="completed")
    db.add(scan)
    db.commit()

    sqr = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best crm", response_text="…", brand_detected=False,
    )
    sqr.sources.append(
        ScanQuerySource(url="https://x.com/a", domain="x.com", title="A", rank=1)
    )
    db.add(sqr)
    db.commit()

    rows = db.query(ScanQuerySource).all()
    assert len(rows) == 1
    assert rows[0].scan_query_result_id == sqr.id
    assert rows[0].fetch_status == "pending"
    assert rows[0].source_type is None


class _FakePerplexity:
    platform = "perplexity"

    def query(self, prompt):
        return PlatformResult(
            text="Acme is great", model="sonar", input_tokens=1, output_tokens=1,
            citations=(SourceCitation(url="https://g2.com/acme", title="G2", rank=1),),
        )


def test_capture_writes_pending_sources_for_perplexity_client_queries(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
               industry="dentist", enabled_platforms=["perplexity"])
    db.add(c)
    scan = Scan(id=uuid.uuid4(), client_id=c.id, status="pending")
    db.add(scan)
    db.commit()

    with patch.object(scan_service, "get_platform_client", return_value=_FakePerplexity()), \
         patch.object(scan_service, "record_llm_usage"), \
         patch.object(scan_service, "extract_position", return_value=None), \
         patch("app.services.remediation_service.sync_remediation_items"), \
         patch("app.services.provenance_service.enrich_scan_sources"), \
         patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0):
        scan_service.run_scan(scan.id, db)

    sources = db.query(ScanQuerySource).all()
    assert sources, "expected captured sources"
    assert all(s.fetch_status == "pending" and s.source_type is None for s in sources)
    assert all(s.domain == "g2.com" for s in sources)


# ── Task 1 (all-platform sources): URL canonicalisation + domain hint ────────


def test_canonical_source_url_strips_utm_params():
    # ChatGPT appends ?utm_source=openai to every cited URL; without stripping,
    # one page would count as two sources for dedupe and flip matching.
    assert (
        canonical_source_url("https://g2.com/acme?utm_source=openai")
        == "https://g2.com/acme"
    )
    assert (
        canonical_source_url("https://g2.com/acme?utm_source=x&utm_medium=y&utm_campaign=z")
        == "https://g2.com/acme"
    )


def test_canonical_source_url_keeps_non_utm_params_in_order():
    assert (
        canonical_source_url("https://x.com/p?id=7&utm_source=openai&page=2")
        == "https://x.com/p?id=7&page=2"
    )


def test_canonical_source_url_strips_fragment():
    assert canonical_source_url("https://x.com/p#reviews") == "https://x.com/p"
    assert canonical_source_url("https://x.com/p?id=1#:~:text=acme") == "https://x.com/p?id=1"


def test_canonical_source_url_leaves_clean_url_unchanged():
    url = "https://www.yelp.com/biz/acme-dental-kuala-lumpur"
    assert canonical_source_url(url) == url


def test_canonical_source_url_returns_unparseable_input_unchanged():
    assert canonical_source_url("") == ""
    assert canonical_source_url("not a url") == "not a url"


def test_source_citation_domain_hint_defaults_to_none():
    c = SourceCitation(url="https://g2.com/acme", title="G2", rank=1)
    assert c.domain_hint is None


def test_gemini_grounding_redirect_host_is_registered():
    assert "vertexaisearch.cloud.google.com" in GROUNDING_REDIRECT_HOSTS


def test_canonical_source_url_keeps_encoding_of_untouched_params():
    assert (
        canonical_source_url("https://x.com/s?q=acme%20dental&utm_source=openai")
        == "https://x.com/s?q=acme%20dental"
    )


# ── Task 6 (all-platform sources): capture on every platform ────────────────


_GEMINI_REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AB"


class _FakePlatform:
    def __init__(self, platform, citations):
        self.platform = platform
        self._citations = citations

    def query(self, prompt):
        # Never names the brand, so position extraction (a Claude call) never runs.
        return PlatformResult(
            text="Several clinics are popular.", model="m", input_tokens=1,
            output_tokens=1, citations=self._citations,
        )


def _run(platform, citations, *, tracked=(), competitors=()):
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="running")
    client_queries = [{"category": "recommendation", "query_text": "best dentist in KL"}]
    with patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0):
        results, _ = scan_service._run_platform_queries(
            platform, _FakePlatform(platform, citations), scan, client,
            list(competitors), [], client_queries, list(tracked),
        )
    return results


def _cite(url, rank=1, title="T", hint=None):
    return SourceCitation(url=url, title=title, rank=rank, domain_hint=hint)


def test_sources_captured_on_every_platform():
    for platform in ("chatgpt", "perplexity", "gemini", "claude"):
        (row,) = _run(platform, (_cite("https://www.g2.com/acme"),))
        assert row.sources_captured is True, platform
        assert [(s.url, s.domain, s.rank) for s in row.sources] == [
            ("https://www.g2.com/acme", "g2.com", 1)
        ], platform


def test_platform_with_no_sources_is_still_marked_captured():
    (row,) = _run("claude", ())
    assert row.sources_captured is True
    assert row.sources == []


def test_gemini_redirect_source_is_filed_under_its_hinted_domain():
    (row,) = _run("gemini", (_cite(_GEMINI_REDIRECT, title=None, hint="yelp.com"),))
    assert [(s.url, s.domain) for s in row.sources] == [(_GEMINI_REDIRECT, "yelp.com")]


def test_redirect_source_without_a_domain_is_skipped_not_misfiled():
    (row,) = _run("gemini", (_cite(_GEMINI_REDIRECT, title=None, hint=None),))
    assert row.sources == []
    assert row.sources_captured is True


def test_overlong_source_title_is_truncated_to_the_column():
    (row,) = _run("chatgpt", (_cite("https://g2.com/a", title="x" * 900),))
    assert len(row.sources[0].title) == 500


def test_tracked_query_samples_capture_sources():
    sample = {
        "query_text": "best dentist in KL", "category": "recommendation",
        "tracked_query_id": uuid.uuid4(), "sample_index": 1, "prompt_version": "v1",
    }
    rows = _run("chatgpt", (_cite("https://g2.com/acme"),), tracked=[sample])
    tracked_rows = [r for r in rows if r.tracked_query_id is not None]
    assert len(tracked_rows) == 1
    assert tracked_rows[0].sources_captured is True
    assert [s.domain for s in tracked_rows[0].sources] == ["g2.com"]


def test_competitor_rows_are_not_captured():
    comp = Competitor(id=uuid.uuid4(), name="Rival", website="https://rival.com")
    rows = _run("chatgpt", (_cite("https://g2.com/acme"),), competitors=[comp])
    comp_rows = [r for r in rows if r.competitor_id is not None]
    assert comp_rows
    assert all(r.sources == [] and r.sources_captured is None for r in comp_rows)


def test_malformed_source_url_costs_one_source_not_the_platform():
    # "http://[::1" raises ValueError in urlparse(...).hostname.
    (row,) = _run("chatgpt", (_cite("http://[::1", rank=1), _cite("https://g2.com/a", rank=2)))
    assert [s.domain for s in row.sources] == ["g2.com"]
