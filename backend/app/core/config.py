# backend/app/core/config.py
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ADMIN_API_KEY is the ONLY control on every endpoint that can spend money
# (scan triggers, report/deliverable generation). A guessable value is a
# direct path to someone else's LLM bill, so production refuses to boot on
# one. Dev and CI are exempt: the committed .env uses a short throwaway key
# and every API test authenticates with it.
_MIN_ADMIN_KEY_LENGTH = 32
# Matched as substrings, not equality: a padded placeholder like
# "changeme-prod-key-000000000000000" clears the length bar but is no secret.
_WEAK_ADMIN_KEY_MARKERS = (
    "changeme", "change-me", "replace-me", "your-admin", "placeholder",
    "password", "secret", "example",
)
# A real key has many distinct characters; `openssl rand -hex 32` yields ~16.
# This catches padding tricks ("a"*64, "abcabcabc...") that pass on length.
_MIN_ADMIN_KEY_DISTINCT_CHARS = 10


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
    # Deployment environment. Set to "production" on Railway to disable the
    # interactive API docs (/docs, /redoc, /openapi.json) so the route surface
    # isn't publicly enumerable. Anything else keeps them on for local dev.
    ENVIRONMENT: str = "development"
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
    # How the rate limiter should read X-Forwarded-For. Match this to the proxy
    # in front of the app — the two families behave oppositely and the wrong
    # setting degrades the limiter silently rather than erroring:
    #   ""  / "0"     no proxy — key on the TCP connection IP, ignore the header
    #   "leftmost"    a STRIPPING edge (Railway, Cloudflare): it discards the
    #                 client's XFF and rebuilds it, so entry 0 is the real
    #                 client. Required on Railway, which also does not promise a
    #                 stable internal hop count.
    #   "1", "2", …   an APPEND-ONLY proxy chain (Caddy, Nginx): the client's own
    #                 XFF is preserved and appended to, so leading entries are
    #                 forgeable and the client is the Nth entry from the right.
    #                 "1" is one reverse proxy, the single-VPS Caddy setup.
    # Any other truthy value means 1 (the original on/off flag form).
    RATE_LIMIT_TRUSTED_PROXY: str = ""
    # ── Cost guardrails ──────────────────────────────────────────────────────
    # USD spend caps enforced before a scan is triggered (scans are the dominant
    # cost driver). A scan over either cap is hard-blocked and the admin alerted.
    # Set a cap to 0 to disable it. BUDGET_CLIENT_MONTHLY_USD is a rolling 30-day
    # window per client; BUDGET_GLOBAL_DAILY_USD is the current UTC day across all
    # clients. Both read the llm_call_logs ledger.
    # Sized against measured cost after the 2026-09-04 rate fix (a scan is
    # ~$2.23; all non-scan LLM work for an active client is ~$0.63/month):
    #   weekly scanning      ~$10.22/client/month  -> ~4x headroom
    #   twice-weekly         ~$19.81/client/month  -> was 99% of the old $20 cap
    # Raised 20 -> 40 so a second weekly scan does not start returning 402s.
    BUDGET_CLIENT_MONTHLY_USD: float = 40.0
    # $50/day covers batch-scanning ~18 clients in one sitting. Revisit past that.
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

    @model_validator(mode="after")
    def _validate_admin_api_key(self):
        """Refuse to start on a weak ADMIN_API_KEY in production.

        Empty is rejected everywhere: require_api_key compares with
        hmac.compare_digest, so an empty configured key would turn any empty
        bearer token into a valid credential.
        """
        key = (self.ADMIN_API_KEY or "").strip()
        if not key:
            raise ValueError("ADMIN_API_KEY must not be empty")
        if self.ENVIRONMENT.strip().lower() != "production":
            return self
        if len(key) < _MIN_ADMIN_KEY_LENGTH:
            raise ValueError(
                f"ADMIN_API_KEY must be at least {_MIN_ADMIN_KEY_LENGTH} characters in "
                f"production (got {len(key)}). Generate one with: openssl rand -hex 32"
            )
        lowered = key.lower()
        marker = next((m for m in _WEAK_ADMIN_KEY_MARKERS if m in lowered), None)
        if marker:
            raise ValueError(
                f"ADMIN_API_KEY looks like a placeholder (contains {marker!r})"
            )
        if len(set(key)) < _MIN_ADMIN_KEY_DISTINCT_CHARS:
            raise ValueError(
                f"ADMIN_API_KEY has only {len(set(key))} distinct characters; it does "
                "not look random. Generate one with: openssl rand -hex 32"
            )
        return self


settings = Settings()
