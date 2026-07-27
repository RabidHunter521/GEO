"""Client work log — the client-safe delivery timeline (spec §3).

Manual-first by design: auto-triggers only ever write `suggested` rows that
the admin reviews, edits, and explicitly publishes. Only `published` rows are
client-visible. Every description is sanitized at write time (CLAUDE.md §2)
even though the admin also sees and can edit it before publishing.
"""
import hashlib
import uuid
from datetime import date

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import (
    WORK_LOG_CATEGORIES,
    WORK_LOG_CATEGORY_LABELS,
    WORK_LOG_STATUSES,
)
from app.core.time import utcnow
from app.models.client import Client
from app.models.work_log_entry import WorkLogEntry
from app.services.language_sanitizer import sanitize_text

logger = structlog.get_logger()


def category_label(entry: WorkLogEntry) -> str:
    """Single source of truth for the display label of an entry's category.

    Both the per-client route and the cross-client review-queue route
    render this same field for the same rows — computing it in two places
    let them drift silently, so both call this instead.
    """
    return WORK_LOG_CATEGORY_LABELS.get(entry.category, entry.category.title())


def suggest(
    client_id: uuid.UUID,
    category: str,
    description: str,
    source_ref: str,
    db: Session,
    entry_date: date | None = None,
) -> WorkLogEntry | None:
    """Create or refresh a `suggested` work-log row for a system event.

    BEST-EFFORT + POST-COMMIT: call this AFTER the triggering operation has
    committed. It owns its own commit and swallows its own failures, so a
    problem here can never undo the work that triggered it (CLAUDE.md §10).

    Idempotent on (client_id, source_ref). A row that the admin has already
    published or dismissed is returned untouched — a re-fired trigger must
    never revert a reviewed decision or overwrite edited wording.
    """
    try:
        if category not in WORK_LOG_CATEGORIES:
            return None
        existing = (
            db.query(WorkLogEntry)
            .filter(WorkLogEntry.client_id == client_id, WorkLogEntry.source_ref == source_ref)
            .first()
        )
        if existing is not None:
            if existing.status != "suggested":
                return existing  # reviewed already — hands off
            existing.description = sanitize_text(description)
            existing.category = category
            if entry_date is not None:
                existing.entry_date = entry_date
            db.commit()
            db.refresh(existing)
            return existing

        entry = WorkLogEntry(
            client_id=client_id,
            category=category,
            description=sanitize_text(description),
            source="auto",
            source_ref=source_ref,
            status="suggested",
            entry_date=entry_date or utcnow().date(),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as exc:
        db.rollback()
        logger.warning(
            "work_log_suggest_failed",
            client_id=str(client_id), source_ref=source_ref, error=str(exc),
        )
        return None


def create_manual(
    client_id: uuid.UUID, category: str, description: str, entry_date: date, db: Session
) -> WorkLogEntry:
    """A manual entry is born published — typing it IS the publish action."""
    if category not in WORK_LOG_CATEGORIES:
        raise ValueError(f"unknown work-log category: {category}")
    entry = WorkLogEntry(
        client_id=client_id,
        category=category,
        description=sanitize_text(description),
        source="manual",
        source_ref=None,
        status="published",
        entry_date=entry_date,
        published_at=utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(entry: WorkLogEntry, patch: dict, db: Session) -> WorkLogEntry:
    """Edit content and/or move status. Editing is allowed after publish so a
    mistake can still be corrected; `published → dismissed` is the undo."""
    if "description" in patch and patch["description"]:
        entry.description = sanitize_text(patch["description"])
    if "category" in patch and patch["category"] in WORK_LOG_CATEGORIES:
        entry.category = patch["category"]
    if "entry_date" in patch and patch["entry_date"]:
        entry.entry_date = patch["entry_date"]
    if "status" in patch and patch["status"] in WORK_LOG_STATUSES:
        new_status = patch["status"]
        if new_status != entry.status:
            entry.status = new_status
            entry.published_at = utcnow() if new_status == "published" else None
    db.commit()
    db.refresh(entry)
    return entry


def list_entries(
    client_id: uuid.UUID, db: Session, status: str | None = None
) -> list[WorkLogEntry]:
    q = db.query(WorkLogEntry).filter(WorkLogEntry.client_id == client_id)
    if status:
        q = q.filter(WorkLogEntry.status == status)
    return q.order_by(desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at)).all()


def published_entries(
    client_id: uuid.UUID, db: Session, since: date | None = None, until: date | None = None
) -> list[WorkLogEntry]:
    """Published rows only — the single source of client-visible truth.

    Status is filtered HERE, at the query, not merely omitted from a schema,
    so a `suggested` row can never leak client-side (spec §3.5).
    """
    q = db.query(WorkLogEntry).filter(
        WorkLogEntry.client_id == client_id, WorkLogEntry.status == "published"
    )
    if since is not None:
        q = q.filter(WorkLogEntry.entry_date >= since)
    if until is not None:
        q = q.filter(WorkLogEntry.entry_date <= until)
    return q.order_by(desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at)).all()


def has_published(client_id: uuid.UUID, db: Session) -> bool:
    """Cheap existence check for the share-view overview flag.

    The overview drives every tab in the client view, so this runs on each page
    load; hydrating the client's whole published history just to test emptiness
    gets slower for the life of the account.
    """
    return (
        db.query(WorkLogEntry.id)
        .filter(WorkLogEntry.client_id == client_id, WorkLogEntry.status == "published")
        .first()
    ) is not None


def published_count_since(client_id: uuid.UUID, db: Session, since: date) -> int:
    return (
        db.query(WorkLogEntry)
        .filter(
            WorkLogEntry.client_id == client_id,
            WorkLogEntry.status == "published",
            WorkLogEntry.entry_date >= since,
        )
        .count()
    )


def suggested_across_clients(db: Session) -> list[tuple[WorkLogEntry, Client]]:
    """Every pending suggestion across all live clients, for the Review Queue.

    Status is filtered HERE, at the query — a `published` or `dismissed` row must
    never reach the queue. Archived clients are excluded to match the per-client
    routes' `_get_client_or_404` behaviour. Ordering is client name then newest
    first, so the page groups cleanly and does not reshuffle between refreshes.
    """
    return (
        db.query(WorkLogEntry, Client)
        .join(Client, Client.id == WorkLogEntry.client_id)
        .filter(WorkLogEntry.status == "suggested", Client.archived_at.is_(None))
        .order_by(
            Client.name, Client.id, desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at)
        )
        .all()
    )


def suggested_count(db: Session) -> int:
    """Count for the sidebar badge.

    Deliberately a COUNT, not len(suggested_across_clients(db)) — this runs on
    every admin page load. Same lesson as has_published(): never hydrate rows to
    produce a number.
    """
    return (
        db.query(WorkLogEntry.id)
        .join(Client, Client.id == WorkLogEntry.client_id)
        .filter(WorkLogEntry.status == "suggested", Client.archived_at.is_(None))
        .count()
    )


_MAX_FLIP_SUGGESTIONS = 5


def suggest_query_flips(client_id: uuid.UUID, db: Session) -> int:
    """One `visibility` suggestion per query that flipped to Seen by AI.

    Reads the existing scan-to-scan diff so the wording matches what the rest
    of the product already computes. Best-effort like every other suggestion.
    """
    try:
        from app.services.scan_diff_service import compute_scan_diff
        diff = compute_scan_diff(client_id, db)
    except Exception as exc:
        logger.warning("work_log_flip_diff_failed", client_id=str(client_id), error=str(exc))
        return 0
    written = 0
    for q in (diff.newly_seen or [])[:_MAX_FLIP_SUGGESTIONS]:
        # Two distinct queries on the same platform can share a 60-char
        # prefix; a full-text hash suffix keeps the source_ref collision
        # resistant while staying inside the String(128) column and
        # remaining greppable via the "query_flip:" prefix.
        digest = hashlib.sha256(q.query_text.encode()).hexdigest()[:8]
        entry = suggest(
            client_id,
            "visibility",
            f'Now seen by AI for: "{q.query_text}"',
            f"query_flip:{q.platform}:{q.query_text[:60]}:{digest}",
            db,
        )
        if entry is not None:
            written += 1
    return written
