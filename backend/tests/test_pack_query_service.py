"""Query generation from pack definitions and APPROVED facts only.

The invariant that matters: a placeholder is filled from an approved,
location-correct fact or the template is dropped. Nothing is guessed, and no
brace ever reaches a model. A scan is what the client is measured on, so a
fabricated query would fabricate the measurement too.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.core.constants import MAX_PACK_QUERIES_PER_SCAN, MAX_PACK_VALUES_PER_PLACEHOLDER
from app.industry_packs.base import category_for
from app.industry_packs.fnb import FNB_PACK
from app.industry_packs.healthcare import HEALTHCARE_PACK
from app.industry_packs.local_services import LOCAL_SERVICES_PACK
from app.services.pack_query_service import ApprovedFact, build_pack_queries

CLIENT_ID = uuid.uuid4()
LOC_A = uuid.uuid4()
LOC_B = uuid.uuid4()


def _client(**kw):
    base = dict(
        id=CLIENT_ID, name="Klinik Sihat", industry="Dental Clinic",
        city="Kuala Lumpur", state="Selangor", country="Malaysia",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _location(location_id=LOC_A, city="Petaling Jaya", **kw):
    base = dict(id=location_id, name="PJ Branch", city=city, state="Selangor",
                country="MY", active=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _competitor(name="Rival Dental"):
    return SimpleNamespace(id=uuid.uuid4(), name=name)


def _fact(fact_type, key, value, location_id=None):
    return ApprovedFact(
        fact_type=fact_type, fact_key=key, value=value, location_id=location_id
    )


def _texts(queries):
    return [q["query_text"] for q in queries]


# --- the core guarantee: nothing is invented --------------------------------

def test_no_query_ever_contains_an_unfilled_placeholder():
    queries = build_pack_queries(
        _client(), [_location()],
        [_fact("treatment", "offered", ["teeth whitening", "root canal"])],
        HEALTHCARE_PACK, [_competitor()],
    )
    assert queries
    for text in _texts(queries):
        assert "{" not in text and "}" not in text, text


def test_a_template_with_no_approved_fact_is_dropped_not_guessed():
    """No treatment facts -> every {service} template disappears entirely."""
    queries = build_pack_queries(
        _client(), [_location()], [], HEALTHCARE_PACK, [],
    )
    for text in _texts(queries):
        assert "service" not in text.lower() or "{" not in text
    # the brand templates still survive, so this is a drop and not a wipeout
    assert any("Klinik Sihat" in t for t in _texts(queries))


def test_empty_and_blank_fact_values_are_treated_as_absent():
    """An approved-but-empty fact must not produce "Where can I get  in KL?"."""
    queries = build_pack_queries(
        _client(), [_location()],
        [_fact("treatment", "offered", ["", "   ", None])],
        HEALTHCARE_PACK, [],
    )
    for text in _texts(queries):
        assert "  " not in text, text
        assert not text.endswith(" in ?"), text


def test_only_approved_facts_are_used():
    """The service accepts ApprovedFact only; there is no path from a draft."""
    queries = build_pack_queries(
        _client(), [_location()],
        [_fact("treatment", "offered", ["implants"])],
        HEALTHCARE_PACK, [],
    )
    assert any("implants" in t for t in _texts(queries))


# --- location correctness ---------------------------------------------------

def test_no_cross_location_fact_leakage():
    """A fact approved for the PJ branch must never be spoken about the KL one."""
    queries = build_pack_queries(
        _client(),
        [_location(LOC_A, city="Petaling Jaya"), _location(LOC_B, city="Ipoh")],
        [_fact("treatment", "offered", ["braces"], location_id=LOC_A)],
        HEALTHCARE_PACK, [],
    )
    for text in _texts(queries):
        if "braces" in text:
            assert "Ipoh" not in text, text


def test_brand_scoped_facts_apply_to_every_location():
    queries = build_pack_queries(
        _client(),
        [_location(LOC_A, city="Petaling Jaya"), _location(LOC_B, city="Ipoh")],
        [_fact("treatment", "offered", ["braces"], location_id=None)],
        HEALTHCARE_PACK, [],
    )
    cities = {t for t in _texts(queries) if "braces" in t}
    assert any("Petaling Jaya" in t for t in cities)
    assert any("Ipoh" in t for t in cities)


def test_inactive_locations_are_excluded():
    queries = build_pack_queries(
        _client(),
        [_location(LOC_A, city="Petaling Jaya"), _location(LOC_B, city="Ipoh", active=False)],
        [_fact("treatment", "offered", ["braces"])],
        HEALTHCARE_PACK, [],
    )
    assert not any("Ipoh" in t for t in _texts(queries))


def test_client_city_is_used_when_no_locations_exist():
    queries = build_pack_queries(_client(), [], [], HEALTHCARE_PACK, [])
    assert any("Kuala Lumpur" in t for t in _texts(queries))


def test_location_templates_are_skipped_when_nothing_provides_a_location():
    """Never "Best dental clinic in None"."""
    client = _client(city=None, state=None, country=None)
    queries = build_pack_queries(client, [], [], HEALTHCARE_PACK, [])
    for text in _texts(queries):
        assert "None" not in text, text
    assert queries, "brand queries should still be built"


# --- determinism, dedupe and caps -------------------------------------------

def test_output_is_deterministic():
    args = (_client(), [_location()],
            [_fact("treatment", "offered", ["a", "b", "c"])], HEALTHCARE_PACK, [_competitor()])
    assert _texts(build_pack_queries(*args)) == _texts(build_pack_queries(*args))


def test_duplicate_query_text_is_collapsed():
    """Two locations in the same city must not double the same question."""
    queries = build_pack_queries(
        _client(),
        [_location(LOC_A, city="Ipoh"), _location(LOC_B, city="Ipoh")],
        [_fact("treatment", "offered", ["braces"])],
        HEALTHCARE_PACK, [],
    )
    texts = _texts(queries)
    assert len(texts) == len(set(texts))


def test_total_query_count_is_capped():
    many = [f"treatment {i}" for i in range(40)]
    queries = build_pack_queries(
        _client(),
        [_location(uuid.uuid4(), city=f"City {i}") for i in range(10)],
        [_fact("treatment", "offered", many), _fact("specialty", "offered", many)],
        HEALTHCARE_PACK, [_competitor(), _competitor("Other")],
    )
    assert len(queries) <= MAX_PACK_QUERIES_PER_SCAN


def test_per_placeholder_fanout_is_capped_before_the_total_cap():
    """40 approved treatments must not become 40 variants of one template."""
    many = [f"treatment {i}" for i in range(40)]
    queries = build_pack_queries(
        _client(), [_location()],
        [_fact("treatment", "offered", many)],
        HEALTHCARE_PACK, [],
    )
    by_template: dict[str, int] = {}
    for q in queries:
        by_template[q["template_id"]] = by_template.get(q["template_id"], 0) + 1
    assert max(by_template.values()) <= MAX_PACK_VALUES_PER_PLACEHOLDER


def test_cap_keeps_the_most_commercially_valuable_queries():
    """When the cap bites it must truncate the tail, so output is ordered by
    commercial intent and then buyer stage — a low-intent awareness question
    can never displace a decision-stage one."""
    many = [f"treatment {i}" for i in range(40)]
    queries = build_pack_queries(
        _client(),
        [_location(uuid.uuid4(), city=f"City {i}") for i in range(6)],
        [_fact("treatment", "offered", many), _fact("specialty", "offered", many)],
        HEALTHCARE_PACK, [_competitor(), _competitor("Other Rival")],
    )
    assert len(queries) == MAX_PACK_QUERIES_PER_SCAN, "expected the cap to bite"

    rank = {"high": 0, "medium": 1, "low": 2}
    intents = [rank[q["commercial_intent"]] for q in queries]
    assert intents == sorted(intents)
    assert queries[0]["commercial_intent"] == "high"


# --- subcategory specialisation ---------------------------------------------
#
# Until now the 8 subcategories per pack did nothing but populate a dropdown:
# a dental practice and a physiotherapy practice were measured on identical
# questions. A template may now name the subcategories it applies to.

def _scoped_texts(pack, subcategory, facts=(), locations=None):
    return _texts(build_pack_queries(
        _client(industry_subcategory=subcategory),
        [_location()] if locations is None else locations,
        list(facts), pack, [],
    ))


def test_a_subcategory_only_query_reaches_that_subcategory():
    texts = _scoped_texts(
        HEALTHCARE_PACK, "diagnostics", [_fact("treatment", "offered", ["MRI scan"])]
    )
    assert any("results" in t and "MRI scan" in t for t in texts), texts


def test_a_subcategory_only_query_does_not_reach_another_subcategory():
    """The whole point: dental and physiotherapy stop scanning identically."""
    facts = [_fact("treatment", "offered", ["MRI scan"])]
    diagnostics = set(_scoped_texts(HEALTHCARE_PACK, "diagnostics", facts))
    physio = set(_scoped_texts(HEALTHCARE_PACK, "physiotherapy", facts))

    assert diagnostics != physio
    assert diagnostics - physio, "diagnostics gained nothing of its own"
    assert physio - diagnostics, "physiotherapy gained nothing of its own"


def test_generic_queries_still_reach_every_subcategory():
    """Specialisation ADDS; it must not fragment the shared measurement, or
    two clients in one pack stop being comparable at all."""
    facts = [_fact("treatment", "offered", ["MRI scan"])]
    generic = {
        t.id for t in HEALTHCARE_PACK.query_templates if not t.subcategories
    }
    assert generic, "fixture assumption: the pack still has generic templates"

    dental = set(_scoped_texts(HEALTHCARE_PACK, "dental", facts))
    physio = set(_scoped_texts(HEALTHCARE_PACK, "physiotherapy", facts))
    assert dental & physio, "no shared questions left between two subcategories"


def test_a_client_with_no_subcategory_gets_only_the_generic_set():
    """Not "all of them": scoped questions contradict each other across
    subcategories, and an unclassified client has no basis for picking."""
    facts = [_fact("treatment", "offered", ["MRI scan"])]
    unclassified = set(_scoped_texts(HEALTHCARE_PACK, None, facts))
    dental = set(_scoped_texts(HEALTHCARE_PACK, "dental", facts))

    assert unclassified <= dental
    assert dental - unclassified


def test_an_unknown_subcategory_falls_back_to_the_generic_set():
    facts = [_fact("treatment", "offered", ["MRI scan"])]
    assert (
        set(_scoped_texts(HEALTHCARE_PACK, "orthodontics", facts))
        == set(_scoped_texts(HEALTHCARE_PACK, None, facts))
    )


def test_subcategory_queries_outrank_generic_ones_at_equal_value():
    """Specialisation has to survive the cap. Two queries of the same
    commercial intent and buyer stage are not equally useful: the one written
    for this exact kind of business is why the subcategory exists."""
    many = [f"treatment {i}" for i in range(40)]
    queries = build_pack_queries(
        _client(industry_subcategory="dental"),
        [_location(uuid.uuid4(), city=f"City {i}") for i in range(6)],
        [_fact("treatment", "offered", many), _fact("specialty", "offered", many)],
        HEALTHCARE_PACK, [_competitor()],
    )
    assert len(queries) == MAX_PACK_QUERIES_PER_SCAN, "expected the cap to bite"

    scoped_by_id = {
        t.id for t in HEALTHCARE_PACK.query_templates if "dental" in t.subcategories
    }
    assert any(q["template_id"] in scoped_by_id for q in queries), (
        "every dental-specific query was crowded out by generic ones"
    )

    # and the existing intent ordering is untouched
    rank = {"high": 0, "medium": 1, "low": 2}
    intents = [rank[q["commercial_intent"]] for q in queries]
    assert intents == sorted(intents)


def test_specialisation_does_not_raise_the_query_cap():
    """Scan spend and AI Citability's denominator both key off this number."""
    queries = build_pack_queries(
        _client(industry_subcategory="dental"),
        [_location(uuid.uuid4(), city=f"City {i}") for i in range(6)],
        [_fact("treatment", "offered", [f"t{i}" for i in range(40)])],
        HEALTHCARE_PACK, [_competitor()],
    )
    assert len(queries) <= MAX_PACK_QUERIES_PER_SCAN


@pytest.mark.parametrize(
    "pack,subcategory",
    [
        (HEALTHCARE_PACK, "dental"),
        (HEALTHCARE_PACK, "physiotherapy"),
        (FNB_PACK, "cafe"),
        (FNB_PACK, "catering"),
        (LOCAL_SERVICES_PACK, "emergency_service"),
        (LOCAL_SERVICES_PACK, "automotive"),
    ],
)
def test_scoped_queries_never_leak_a_placeholder(pack, subcategory):
    texts = _scoped_texts(pack, subcategory, [
        _fact("treatment", "offered", ["x"]), _fact("service", "catalog", ["x"]),
        _fact("cuisine", "types", ["x"]), _fact("menu", "signature_dishes", ["x"]),
        _fact("occasion", "suitable_for", ["birthdays"]),
    ])
    assert texts
    for text in texts:
        assert "{" not in text and "}" not in text, text


# --- category mapping -------------------------------------------------------

def test_every_query_lands_in_an_existing_scan_category():
    for pack in (HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK):
        queries = build_pack_queries(
            _client(), [_location()],
            [_fact("treatment", "offered", ["x"]), _fact("service", "catalog", ["x"]),
             _fact("cuisine", "types", ["x"]), _fact("menu", "signature_dishes", ["x"])],
            pack, [_competitor()],
        )
        for q in queries:
            assert q["category"] in ("brand", "comparison", "recommendation", "local")


def test_comparison_queries_are_capped_by_competitor_count():
    """Matches legacy behaviour: no competitors means no comparison queries."""
    queries = build_pack_queries(_client(), [_location()], [], HEALTHCARE_PACK, [])
    assert not [q for q in queries if q["category"] == "comparison"]


def test_a_competitor_query_names_a_real_competitor():
    rival = _competitor("Rival Dental")
    queries = build_pack_queries(_client(), [_location()], [], HEALTHCARE_PACK, [rival])
    comparisons = [q for q in queries if q["category"] == "comparison"]
    assert comparisons
    for q in comparisons:
        assert "Rival Dental" in q["query_text"]


def test_client_queries_never_carry_a_competitor_id():
    """competitor_id marks a row as being ABOUT a competitor; comparison queries
    are still the client's own rows, exactly as in the legacy builder."""
    queries = build_pack_queries(
        _client(), [_location()], [], HEALTHCARE_PACK, [_competitor()]
    )
    assert all(q["competitor_id"] is None for q in queries)


def test_pack_queries_are_not_governed_tracked_queries():
    """Why the query cap and the benchmark coverage band are independent.

    coverage_band_for counts DISTINCT tracked_query_id on non-control rows.
    Pack client queries leave that NULL — the governed portfolio is sampled
    separately by query_sampling_service — so MAX_PACK_QUERIES_PER_SCAN cannot
    move a client between cohorts. constants.py states this; this test is what
    stops it quietly becoming false.
    """
    queries = build_pack_queries(
        _client(industry_subcategory="dental"), [_location()],
        [_fact("treatment", "offered", ["teeth whitening"])], HEALTHCARE_PACK, [],
    )
    assert queries
    assert all("tracked_query_id" not in q for q in queries)
    assert all("sample_index" not in q for q in queries)


def test_no_query_is_marked_as_a_control():
    """Control queries are admin-authored benchmarks and must stay separate."""
    queries = build_pack_queries(_client(), [_location()], [], HEALTHCARE_PACK, [])
    assert all(not q.get("is_control") for q in queries)


# --- shape ------------------------------------------------------------------

def test_queries_expose_the_scan_engine_contract():
    queries = build_pack_queries(_client(), [_location()], [], HEALTHCARE_PACK, [])
    for q in queries:
        assert set(q) >= {"category", "query_text", "competitor_id"}


@pytest.mark.parametrize("pack", [HEALTHCARE_PACK, FNB_PACK, LOCAL_SERVICES_PACK])
def test_every_pack_produces_queries_for_a_bare_client(pack):
    """A client with a pack but no approved facts still gets brand coverage."""
    queries = build_pack_queries(_client(), [], [], pack, [])
    assert queries
    assert all("{" not in q["query_text"] for q in queries)


def test_category_rule_matches_the_templates_it_describes():
    healthcare = {q.id: category_for(q) for q in HEALTHCARE_PACK.query_templates}
    assert healthcare["brand_overview"] == "brand"
    assert healthcare["brand_vs_competitor"] == "comparison"
    assert healthcare["local_best"] == "recommendation"
    assert healthcare["treatment_cost"] == "local"


# --- the Vault boundary -----------------------------------------------------
#
# Everything above is pure. approved_facts_for is where the scan path actually
# reads the Truth Vault, so it needs a real database: it is the only place a
# draft, retired or wrong-location value could physically reach a live query.

def _seed_fact(db, client_id, fact_type, key, value, *, location_id=None, status="approved"):
    from datetime import datetime

    from app.models.truth_fact import TruthFact, TruthFactVersion

    fact = TruthFact(
        client_id=client_id, location_id=location_id, fact_type=fact_type, fact_key=key
    )
    db.add(fact)
    db.flush()
    version = TruthFactVersion(
        truth_fact_id=fact.id, value_json=value, status=status,
        effective_from=datetime(2020, 1, 1) if status == "approved" else None,
        approved_at=datetime(2020, 1, 1) if status == "approved" else None,
        approved_by="admin" if status == "approved" else None,
    )
    if status == "retired":
        version.status = "approved"
        version.effective_to = datetime(2020, 6, 1)
    db.add(version)
    db.flush()
    return fact


def test_approved_facts_for_reads_only_approved_current_facts(db):
    from app.models.business_location import BusinessLocation
    from app.models.client import Client
    from app.services.pack_query_service import approved_facts_for

    client = Client(name="Klinik", website="https://k.my", industry="dental clinic")
    db.add(client)
    db.flush()
    branch = BusinessLocation(
        client_id=client.id, name="PJ", slug="pj", city="Petaling Jaya", active=True
    )
    closed = BusinessLocation(
        client_id=client.id, name="Old", slug="old", city="Ipoh", active=False
    )
    db.add_all([branch, closed])
    db.flush()

    _seed_fact(db, client.id, "treatment", "offered", ["braces"])
    _seed_fact(db, client.id, "treatment", "price_range", ["secret"], status="draft")
    _seed_fact(db, client.id, "specialty", "offered", ["gone"], status="retired")
    _seed_fact(db, client.id, "facility", "services", ["xray"], location_id=branch.id)
    _seed_fact(db, client.id, "facility", "services", ["closed"], location_id=closed.id)
    db.commit()

    facts = approved_facts_for(client, db)
    values = {str(f.value) for f in facts}

    assert any("braces" in v for v in values), "approved brand fact must be present"
    assert not any("secret" in v for v in values), "a DRAFT fact reached the scan path"
    assert not any("gone" in v for v in values), "a RETIRED fact reached the scan path"
    assert any("xray" in v for v in values), "active location fact must be present"
    assert not any("closed" in v for v in values), "an INACTIVE location's fact leaked"


def test_approved_facts_carry_their_location_scope(db):
    from app.models.business_location import BusinessLocation
    from app.models.client import Client
    from app.services.pack_query_service import approved_facts_for

    client = Client(name="Klinik", website="https://k.my", industry="dental clinic")
    db.add(client)
    db.flush()
    branch = BusinessLocation(
        client_id=client.id, name="PJ", slug="pj", city="Petaling Jaya", active=True
    )
    db.add(branch)
    db.flush()
    _seed_fact(db, client.id, "treatment", "offered", ["brandwide"])
    _seed_fact(db, client.id, "facility", "services", ["local"], location_id=branch.id)
    db.commit()

    by_type = {f.fact_type: f for f in approved_facts_for(client, db)}
    assert by_type["treatment"].location_id is None
    assert by_type["facility"].location_id == branch.id


# --- cross-pack wiring ------------------------------------------------------
#
# _FACT_SOURCES is a hand-written map from placeholder to (fact_type, fact_key).
# A wrong entry does not raise: the placeholder simply never fills, its template
# is silently dropped, and the client is quietly scanned on fewer questions than
# the pack promises. Same failure class as a risk rule targeting a fact nothing
# declares, so it gets the same structural guard.

def test_every_fact_source_mapping_matches_a_declared_field():
    from app.industry_packs import registry
    from app.services.pack_query_service import _FACT_SOURCES

    declared = {(f.fact_type, f.key) for p in registry.all_packs() for f in p.truth_fields}
    dead = [
        (placeholder, pair)
        for placeholder, pairs in _FACT_SOURCES.items()
        for pair in pairs
        if pair not in declared
    ]
    assert not dead, f"_FACT_SOURCES points at facts no pack declares: {dead}"


def test_every_fact_backed_placeholder_has_a_source_mapping():
    from app.industry_packs import registry
    from app.industry_packs.base import placeholders_in
    from app.services.pack_query_service import _FACT_SOURCES

    from_client = {"brand", "competitor", "industry", "city", "location", "area"}
    missing = [
        (pack.key, template.id, placeholder)
        for pack in registry.all_packs()
        for template in pack.query_templates
        for placeholder in placeholders_in(template.template)
        if placeholder not in from_client and placeholder not in _FACT_SOURCES
    ]
    assert not missing, f"templates use placeholders nothing can fill: {missing}"


def test_no_template_is_permanently_unfillable_for_its_own_pack():
    """A template whose pack declares no source for its placeholder can never
    run — it would look like query coverage while producing nothing, ever."""
    from app.industry_packs import registry
    from app.industry_packs.base import placeholders_in
    from app.services.pack_query_service import _FACT_SOURCES

    problems = []
    for pack in registry.all_packs():
        fields = {(f.fact_type, f.key) for f in pack.truth_fields}
        for template in pack.query_templates:
            for placeholder in placeholders_in(template.template):
                sources = _FACT_SOURCES.get(placeholder)
                if sources and not any(pair in fields for pair in sources):
                    problems.append(f"{pack.key}.{template.id} needs {placeholder}")
    assert not problems, f"templates that can never fill: {problems}"


# --- the run_scan seam ------------------------------------------------------
#
# Every test above exercises a unit. This exercises the JOIN between them: that
# run_scan actually resolves the client's pack, loads its active locations and
# approved facts, and hands the PACK's queries to the platform worker. Each unit
# passing does not prove the seam is wired, and the seam is the whole feature.

def _scan_fixture(db, industry_pack=None):
    from datetime import datetime

    from app.models.client import Client
    from app.models.scan import Scan

    client = Client(
        name="Klinik Sihat", website="https://k.my", industry="dental clinic",
        city="Kuala Lumpur", state="Selangor", industry_pack=industry_pack,
        enabled_platforms=["gemini"],
    )
    db.add(client)
    db.flush()
    scan = Scan(client_id=client.id, status="pending", triggered_at=datetime(2026, 1, 1))
    db.add(scan)
    db.commit()
    return client, scan


def _captured_queries(db, scan, monkeypatch):
    """Run run_scan far enough to capture what the platform worker receives."""
    from app.services import scan_service

    captured = {}

    def _fake_platform_queries(
        platform, pc, scan_, client_, competitors, controls, client_queries,
        tracked_query_samples=(),
    ):
        captured["queries"] = client_queries
        return [], []

    monkeypatch.setattr(scan_service, "_run_platform_queries", _fake_platform_queries)
    monkeypatch.setattr(scan_service, "get_platform_client", lambda p: object())
    try:
        scan_service.run_scan(scan.id, db)
    except Exception:
        # Scoring/alerting after the fan-out is out of scope here; the capture
        # has already happened by then.
        pass
    return captured.get("queries", [])


def test_run_scan_hands_pack_queries_to_the_platform_worker(db, monkeypatch):
    from app.models.truth_fact import TruthFact, TruthFactVersion
    from datetime import datetime

    client, scan = _scan_fixture(db, industry_pack="healthcare")
    fact = TruthFact(client_id=client.id, fact_type="treatment", fact_key="offered")
    db.add(fact)
    db.flush()
    db.add(TruthFactVersion(
        truth_fact_id=fact.id, value_json=["dental implants"], status="approved",
        effective_from=datetime(2020, 1, 1), approved_at=datetime(2020, 1, 1),
        approved_by="admin",
    ))
    db.commit()

    queries = _captured_queries(db, scan, monkeypatch)
    texts = [q["query_text"] for q in queries]

    assert texts, "run_scan built no client queries at all"
    # the approved fact reached a real query — proof the whole chain is wired
    assert any("dental implants" in t for t in texts), texts
    # and it is the PACK's phrasing, not the legacy template set
    assert not any(t.startswith("Tell me about") for t in texts), texts
    assert all("{" not in t for t in texts)


def test_run_scan_keeps_unpacked_clients_on_the_legacy_templates(db, monkeypatch):
    """The regression that would matter most: an existing client's measurement
    must not change because Phase 4 shipped."""
    client, scan = _scan_fixture(db, industry_pack=None)

    texts = [q["query_text"] for q in _captured_queries(db, scan, monkeypatch)]

    assert any(t.startswith("Tell me about") for t in texts), texts
