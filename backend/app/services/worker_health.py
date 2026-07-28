# backend/app/services/worker_health.py
"""Is anyone actually consuming the Celery queue?

Enqueueing is not the same as running. With the worker stopped, .delay()
succeeds against a live Redis and the job waits forever, so the UI reported
"queued" for work that would never start. Routes that promise the admin a
background result should check this first and fail loudly instead.

Deliberately NOT used by the scan flow: scans are long and already surface
progress through their own status column. This is for fire-and-forget
endpoints whose only feedback is "we started it".
"""
import structlog

from workers.celery_app import celery_app

logger = structlog.get_logger()

# Kept short: this runs inline on an admin request, and a worker that cannot
# answer a ping in a second is not going to pick the job up promptly either.
PING_TIMEOUT_SECONDS = 1.0


def workers_online(timeout: float = PING_TIMEOUT_SECONDS) -> bool:
    """True when at least one Celery worker answers a broadcast ping.

    Never raises: an unreachable broker is reported as "no workers", which is
    the same actionable answer from the admin's point of view.
    """
    try:
        replies = celery_app.control.ping(timeout=timeout)
    except Exception as exc:
        logger.warning("worker_ping_failed", error=str(exc))
        return False
    return bool(replies)
