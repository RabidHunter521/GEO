import boto3
from botocore.config import Config
from app.core.config import settings


def _s3():
    if not settings.CLOUDFLARE_R2_ENDPOINT_URL:
        raise RuntimeError("CLOUDFLARE_R2_ENDPOINT_URL is not configured")
    return boto3.client(
        "s3",
        endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT_URL,
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )


def upload_pdf(key: str, pdf_bytes: bytes) -> str:
    """Upload PDF bytes to R2; return public URL."""
    _s3().put_object(
        Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    return f"{settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')}/{key}"


def upload_image(key: str, image_bytes: bytes, content_type: str) -> str:
    """Upload image bytes to R2; return public URL. Used for client logos."""
    _s3().put_object(
        Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
        CacheControl="public, max-age=31536000",
    )
    return f"{settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')}/{key}"


def download_pdf(key: str) -> bytes:
    """Download PDF bytes from R2 by key."""
    resp = _s3().get_object(Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME, Key=key)
    return resp["Body"].read()
