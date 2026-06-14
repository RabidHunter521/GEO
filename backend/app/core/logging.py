"""structlog configuration for the API process.

Adds merge_contextvars so values bound per-request (e.g. request_id) appear on
every log line emitted while handling that request.
"""
import structlog


def configure_logging() -> None:
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
