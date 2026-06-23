# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    # Empty default = platform marked unavailable at scan time, backend still boots.
    # Consistent across all four scan platforms; per-client toggles already let a
    # client run without any one of them (ANTHROPIC stays required — it powers the
    # non-platform Claude features the product depends on).
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    PERPLEXITY_API_KEY: str = ""
    ADMIN_API_KEY: str
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    ANTHROPIC_API_KEY: str
    RESEND_API_KEY: str
    # Optional Telegram admin alerts — both empty = disabled (alerts still email)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    CLOUDFLARE_R2_ENDPOINT_URL: str = ""
    CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
    CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
    # Private bucket — report PDFs. No public read; served only via presigned URLs.
    CLOUDFLARE_R2_BUCKET_NAME: str = "seenby-reports"
    # Public bucket — client logos. Must allow public read: logos are embedded in
    # emails and the public client view and must outlive any presign window.
    CLOUDFLARE_R2_PUBLIC_BUCKET_NAME: str = ""
    # Public base URL (custom domain or r2.dev) mapped to the PUBLIC bucket above.
    CLOUDFLARE_R2_PUBLIC_URL: str = ""
    # Set to any non-empty value when the app sits behind a reverse proxy
    # (Nginx, Caddy, etc.). Causes the rate limiter to key on the rightmost
    # X-Forwarded-For entry (proxy-appended) rather than the TCP connection IP.
    RATE_LIMIT_TRUSTED_PROXY: str = ""
    # ── Cost guardrails ──────────────────────────────────────────────────────
    # USD spend caps enforced before a scan is triggered (scans are the dominant
    # cost driver). A scan over either cap is hard-blocked and the admin alerted.
    # Set a cap to 0 to disable it. BUDGET_CLIENT_MONTHLY_USD is a rolling 30-day
    # window per client; BUDGET_GLOBAL_DAILY_USD is the current UTC day across all
    # clients. Both read the llm_call_logs ledger.
    BUDGET_CLIENT_MONTHLY_USD: float = 20.0
    BUDGET_GLOBAL_DAILY_USD: float = 50.0
    # Provider circuit breaker: after this many consecutive 429/402 responses
    # from one scan platform (within a short window), stop calling it for the
    # cooldown so a rate-limited/over-quota provider isn't hammered. Redis-backed
    # so it is shared across the API and Celery workers; if Redis is unavailable
    # the breaker degrades to a no-op and never blocks a scan.
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 300

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
