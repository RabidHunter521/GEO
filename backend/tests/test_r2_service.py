from unittest.mock import MagicMock, patch

import pytest

from app.services import r2_service
from app.services.r2_service import upload_pdf, upload_image, download_pdf, presigned_pdf_url


@pytest.fixture(autouse=True)
def _reset_cached_client():
    # The client is cached module-level; clear it so each test builds a fresh
    # one under its own boto3/settings patch.
    r2_service.reset_s3_client()
    yield
    r2_service.reset_s3_client()


def _mock_settings(**overrides):
    m = MagicMock()
    m.CLOUDFLARE_R2_ENDPOINT_URL = "https://acct.r2.cloudflarestorage.com"
    m.CLOUDFLARE_R2_ACCESS_KEY_ID = "key123"
    m.CLOUDFLARE_R2_SECRET_ACCESS_KEY = "secret456"
    m.CLOUDFLARE_R2_BUCKET_NAME = "seenby-reports"
    m.CLOUDFLARE_R2_PUBLIC_BUCKET_NAME = "seenby-public"
    m.CLOUDFLARE_R2_PUBLIC_URL = "https://pub.seenby.my"
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def test_upload_pdf_calls_put_object_with_correct_args():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    mock_s3.put_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
        Body=b"pdfdata",
        ContentType="application/pdf",
    )


def test_upload_pdf_returns_storage_key():
    """Report PDFs live in the private bucket and are only ever served via a
    presigned URL, so upload_pdf returns the storage key (the stored r2_url is
    a reference, not a live public link)."""
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        key = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert key == "reports/abc/20260601.pdf"


def test_upload_pdf_does_not_require_public_url():
    """The private report bucket has no public base, so upload_pdf must not
    depend on CLOUDFLARE_R2_PUBLIC_URL."""
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings(CLOUDFLARE_R2_PUBLIC_URL="")):
        key = upload_pdf("reports/abc/20260601.pdf", b"pdfdata")
    assert key == "reports/abc/20260601.pdf"


def test_upload_image_uploads_to_public_bucket_and_returns_public_url():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        url = upload_image("logos/abc.png", b"imgdata", "image/png")
    assert url == "https://pub.seenby.my/logos/abc.png"
    mock_s3.put_object.assert_called_once_with(
        Bucket="seenby-public",
        Key="logos/abc.png",
        Body=b"imgdata",
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )


def test_upload_image_strips_trailing_slash_from_public_url():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings(CLOUDFLARE_R2_PUBLIC_URL="https://pub.seenby.my/")):
        url = upload_image("logos/abc.png", b"imgdata", "image/png")
    assert url == "https://pub.seenby.my/logos/abc.png"


def test_upload_image_requires_public_bucket_configured():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings(CLOUDFLARE_R2_PUBLIC_BUCKET_NAME="")):
        with pytest.raises(RuntimeError):
            upload_image("logos/abc.png", b"imgdata", "image/png")


def test_download_pdf_returns_bytes_from_s3():
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"pdf-content")}
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        result = download_pdf("reports/abc/20260601.pdf")
    assert result == b"pdf-content"
    mock_s3.get_object.assert_called_once_with(
        Bucket="seenby-reports",
        Key="reports/abc/20260601.pdf",
    )


def test_presigned_pdf_url_signs_get_object_with_ttl():
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://acct.r2.cloudflarestorage.com/signed?sig=x"
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        url = presigned_pdf_url("reports/abc/20260601.pdf")
    assert url == "https://acct.r2.cloudflarestorage.com/signed?sig=x"
    mock_s3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "seenby-reports", "Key": "reports/abc/20260601.pdf"},
        ExpiresIn=r2_service.PRESIGNED_URL_TTL_SECONDS,
    )


def test_presigned_pdf_url_honors_custom_expiry():
    mock_s3 = MagicMock()
    with patch("app.services.r2_service.boto3.client", return_value=mock_s3), \
         patch("app.services.r2_service.settings", _mock_settings()):
        presigned_pdf_url("reports/abc/20260601.pdf", expires_in=120)
    _, kwargs = mock_s3.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == 120
