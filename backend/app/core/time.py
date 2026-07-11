from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime — drop-in replacement for the deprecated datetime.utcnow().

    Every DateTime column in this project (except llm_call_logs.called_at) is
    declared without timezone=True, so it stores naive UTC values. Returning
    tzinfo=None here preserves that exact behavior instead of introducing
    aware/naive comparison bugs against existing rows.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
