"""structlog configuration for the API process.

Adds merge_contextvars so values bound per-request (e.g. request_id) appear on
every log line emitted while handling that request.
"""
import logging
import re

import structlog

# URL path segments that ARE credentials: one-time invite/reset links and
# client-view share tokens. Logs keep a short prefix (enough to correlate a
# support request) and never the usable token.
_SECRET_PATH = re.compile(r"(/auth/link/|/auth/invite/|/view/)([^/?\s\"]+)")


def redact_path(path: str) -> str:
    return _SECRET_PATH.sub(lambda m: f"{m.group(1)}{m.group(2)[:6]}…", path)


class _RedactAccessLog(logging.Filter):
    """uvicorn.access logs the request line with the full path."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact_path(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _RedactAccessLog) for f in access.filters):
        access.addFilter(_RedactAccessLog())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        cache_logger_on_first_use=True,
    )
