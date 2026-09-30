"""Every client-facing footer carries SeenBy's legal entity + SSM number."""
from unittest.mock import MagicMock

from app.core.constants import (
    COMPANY_IDENTITY_LINE,
    COMPANY_LEGAL_NAME,
    COMPANY_REGISTRATION_NUMBER,
)

ESCAPED = COMPANY_IDENTITY_LINE.replace("&", "&amp;")


def test_identity_line_names_entity_and_ssm_number():
    assert COMPANY_LEGAL_NAME in COMPANY_IDENTITY_LINE
    assert COMPANY_REGISTRATION_NUMBER in COMPANY_IDENTITY_LINE
    assert COMPANY_REGISTRATION_NUMBER.isdigit() and len(COMPANY_REGISTRATION_NUMBER) == 12


def test_pdf_report_cover_footer_and_page_footer():
    from app.services.report_service import _CSS, _build_report_html
    from tests.test_report_service import _make_report_data

    client = MagicMock()
    client.name = "Acme Corp"
    out = _build_report_html(client, _make_report_data())
    assert out.count(ESCAPED) >= 2  # cover footer + closing footer
    assert f"{COMPANY_LEGAL_NAME} ({COMPANY_REGISTRATION_NUMBER})" in _CSS  # every page
    assert "{company_identity_css}" not in _CSS


def test_digest_email_footer():
    from app.services.digest_service import _build_email_html
    from tests.test_digest_service import _digest_client, _digest_data

    assert ESCAPED in _build_email_html(_digest_client(), _digest_data())


def test_report_email_footer():
    from app.services.report_service import _build_report_email_html

    client = MagicMock()
    client.name = "Acme Corp"
    report = MagicMock()
    report.overall_score = 72.0
    out = _build_report_email_html(client, report, "May 2026")
    assert ESCAPED in out
