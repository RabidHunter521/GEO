"""Pick the single 'headline battle' — the most important lost query, the rival
winning it, and the one move (an existing content brief) to flip it.

Deterministic and LLM-free: reuses win_loss_service classification and reads any
brief that already exists. Never generates a brief (no content_brief_service
import) so it is safe to call from automated digest/report flows.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.constants import PLATFORM_LABELS
from app.services.win_loss_service import compute_win_loss

# recommendation/local are the only WIN_LOSS_CATEGORIES; rank recommendation first
# (highest buyer intent). Unknown categories sort last.
_CATEGORY_PRIORITY = {"recommendation": 0, "local": 1}
_UNKNOWN_CATEGORY_RANK = 9


@dataclass
class HeadlineBattle:
    rival_name: str
    query_text: str
    platform_label: str
    category: str
    move_title: str | None
    move_angle: str | None


def _primary_threat(lost_entries) -> str | None:
    """The competitor named in the most lost battles (tie broken by name)."""
    counts: dict[str, int] = {}
    for e in lost_entries:
        for name in e.competitors_seen:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _sort_key(entry, primary: str | None):
    cat_rank = _CATEGORY_PRIORITY.get(entry.category, _UNKNOWN_CATEGORY_RANK)
    has_primary = 0 if (primary and primary in entry.competitors_seen) else 1
    return (cat_rank, has_primary, entry.query_text)


def select_headline_battle(client_id: uuid.UUID, db: Session) -> HeadlineBattle | None:
    wl = compute_win_loss(client_id, db)
    lost = [e for e in wl.entries if e.outcome == "lost"]
    if not lost:
        return None
    primary = _primary_threat(lost)
    chosen = sorted(lost, key=lambda e: _sort_key(e, primary))[0]
    rival = (
        primary
        if (primary and primary in chosen.competitors_seen)
        else (chosen.competitors_seen[0] if chosen.competitors_seen else None)
    )
    if rival is None:
        return None  # a 'lost' outcome always has >=1 competitor; guard anyway
    brief = chosen.brief
    return HeadlineBattle(
        rival_name=rival,
        query_text=chosen.query_text,
        platform_label=PLATFORM_LABELS.get(chosen.platform, chosen.platform.title()),
        category=chosen.category,
        move_title=brief.title if brief else None,
        move_angle=brief.angle if brief else None,
    )
