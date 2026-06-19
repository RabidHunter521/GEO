import threading

import boto3
from botocore.config import Config

from app.core.config import settings

# boto3 client construction is expensive (loads botocore data + builds the
# session). The client is thread-safe for calls, so cache a single instance
# instead of rebuilding it on every upload/download.
_client = None
_lock = threading.Lock()

_CONFIG = Config(
    signature_version="s3v4",
    connect_timeout=10,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "standard"},
)


def _s3():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                if not settings.CLOUDFLARE_R2_ENDPOINT_URL:
                    raise RuntimeError("CLOUDFLARE_R2_ENDPOINT_URL is not configured")
                _client = boto3.client(
                    "s3",
                    endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT_URL,
                    aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
                    config=_CONFIG,
                )
    return _client


def reset_s3_client() -> None:
    """Drop the cached client. For tests that patch boto3/settings per case."""
    global _client
    with _lock:
        _client = None


def _public_base() -> str:
    """Public R2 base URL, validated. Without it we'd build a host-less link like
    "/reports/<key>" that silently renders as a dead download button."""
    base = settings.CLOUDFLARE_R2_PUBLIC_URL
    if not base:
        raise RuntimeError(
            "CLOUDFLARE_R2_PUBLIC_URL is not configured — cannot build a public "
            "download URL for uploaded files."
        )
    return base.rstrip("/")


def upload_pdf(key: str, pdf_bytes: bytes) -> str:
    """Upload PDF bytes to R2; return public URL."""
    public_base = _public_base()
    _s3().put_object(
        Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    return f"{public_base}/{key}"


def upload_image(key: str, image_bytes: bytes, content_type: str) -> str:
    """Upload image bytes to R2; return public URL. Used for client logos."""
    public_base = _public_base()
    _s3().put_object(
        Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
        CacheControl="public, max-age=31536000",
    )
    return f"{public_base}/{key}"


def download_pdf(key: str) -> bytes:
    """Download PDF bytes from R2 by key."""
    resp = _s3().get_object(Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME, Key=key)
    return resp["Body"].read()


# Default lifetime for a report download link. Long enough that a client can
# open the dashboard and click through, short enough that a leaked URL (forwarded
# email, shoulder-surf) stops working within the hour.
PRESIGNED_URL_TTL_SECONDS = 3600


def presigned_pdf_url(key: str, expires_in: int = PRESIGNED_URL_TTL_SECONDS) -> str:
    """Return a short-lived signed GET URL for an object in the (private) R2
    bucket. This is the access path for report PDFs: the stored r2_url is a
    permanent public link and is only safe while the bucket is private — serving
    a freshly signed URL per request means access expires and can be revoked by
    rotating R2 keys. Requires the bucket to be private to add any protection."""
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.CLOUDFLARE_R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
