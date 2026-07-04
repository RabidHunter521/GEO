from app.services import provenance_service as ps


def test_normalize_domain_strips_www_and_scheme():
    assert ps.normalize_domain("https://www.Acme.com/best-crm") == "acme.com"
    assert ps.normalize_domain("http://blog.acme.com/x") == "blog.acme.com"
    assert ps.normalize_domain("acme.com") == "acme.com"


def test_normalize_domain_handles_garbage():
    assert ps.normalize_domain("") == ""
    assert ps.normalize_domain("not a url") == ""


def test_classify_source_type():
    comp_domains = {"rival.com": "comp-1"}
    assert ps.classify_source_type("acme.com", "acme.com", comp_domains) == "client_owned"
    assert ps.classify_source_type("rival.com", "acme.com", comp_domains) == "competitor_owned"
    assert ps.classify_source_type("g2.com", "acme.com", comp_domains) == "third_party"
