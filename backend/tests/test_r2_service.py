import pytest
from unittest.mock import MagicMock, patch


def _mock_settings(**kwargs):
    defaults = dict(
        CLOUDFLARE_R2_ENDPOINT_URL="https://acct.r2.cloudflarestorage.com",
        CLOUDFLARE_R2_ACCESS_KEY_ID="key123",
        CLOUDFLARE_R2_SECRET_ACCESS_KEY="secret456",
        CLOUDFLARE_R2_BUCKET_NAME="seenby-reports",
        CLOUDFLARE_R2_PUBLIC_URL="https://pub.seenby.my",
    )
    defaults.update(kwargs)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def test_upload_pdf_calls_put_object_with_correct_args():
    mock_s3 = MagicMock()
    mock_settings = _mock_settings()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", mock_settings):
        from app.services.r2_service import upload_pdf
        upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    mock_s3.put_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
        Body=b"pdfdata",
        ContentType="application/pdf",
    )


def test_upload_pdf_returns_public_url():
    mock_s3 = MagicMock()
    mock_settings = _mock_settings()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", mock_settings):
        from app.services.r2_service import upload_pdf
        url = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert url == "https://pub.seenby.my/reports/abc/20260601.pdf"


def test_upload_pdf_strips_trailing_slash_from_public_url():
    mock_s3 = MagicMock()
    mock_settings = _mock_settings(CLOUDFLARE_R2_PUBLIC_URL="https://pub.seenby.my/")
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", mock_settings):
        from app.services.r2_service import upload_pdf
        url = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert url == "https://pub.seenby.my/reports/abc/20260601.pdf"


def test_download_pdf_returns_bytes_from_s3():
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"pdf-content")}
    mock_settings = _mock_settings()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", mock_settings):
        from app.services.r2_service import download_pdf
        result = download_pdf("reports/abc/20260601.pdf")
    assert result == b"pdf-content"
    mock_s3.get_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
    )
