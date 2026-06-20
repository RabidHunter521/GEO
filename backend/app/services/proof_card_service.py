"""Select client-safe 'proof cards' from a scan's client-owned results.

A proof card is one verbatim AI answer, reduced to a single redacted sentence:
a WIN (the brand is named) or a LOSS (a competitor is named and the brand is
absent). The raw response_text is never carried on a ProofCard — only the
finished, redacted excerpt — so this can feed the public client view directly.
"""
from dataclasses import dataclass

from app.services import snippet_service

# Lower rank = surfaced first. Recommendation/local are the answers that read as
# "who got recommended", so they make the strongest proof.
_CATEGORY_PRIORITY = {"recommendation": 0, "local": 1, "brand": 2, "comparison": 3}
_LOSS_CATEGORIES = {"recommendation", "local"}
_UNKNOWN_CATEGORY_RANK = 9
_ABSENT_POSITION = 99


@dataclass
class ProofCard:
    kind: str       # "win" | "loss"
    platform: str   # raw platform code (caller maps to a label)
    category: str
    excerpt: str


def _sort_key(result) -> tuple[int, int]:
    cat_rank = _CATEGORY_PRIORITY.get(result.category, _UNKNOWN_CATEGORY_RANK)
    pos = result.recommendation_position if result.recommendation_position is not None else _ABSENT_POSITION
    return (cat_rank, pos)


def result_excerpt(result, brand: str, competitors: list[str]) -> tuple[str | None, str | None]:
    """(kind, excerpt) for one client-owned result, or (None, None)."""
    if result.brand_detected:
        ex = snippet_service.build_excerpt(result.response_text or "", brand, competitors)
        return ("win", ex) if ex else (None, None)
    if result.category in _LOSS_CATEGORIES:
        ex = snippet_service.build_loss_excerpt(result.response_text or "", brand, competitors)
        return ("loss", ex) if ex else (None, None)
    return (None, None)


def select_proof_cards(
    results,
    brand: str,
    competitors: list[str],
    win_cap: int = 2,
    loss_cap: int = 1,
) -> list[ProofCard]:
    """Best wins first, then the best loss, capped. Empty when nothing qualifies."""
    wins: list[ProofCard] = []
    losses: list[ProofCard] = []
    for r in sorted(results, key=_sort_key):
        kind, ex = result_excerpt(r, brand, competitors)
        if kind == "win" and len(wins) < win_cap:
            wins.append(ProofCard("win", r.platform, r.category, ex))
        elif kind == "loss" and len(losses) < loss_cap:
            losses.append(ProofCard("loss", r.platform, r.category, ex))
        if len(wins) >= win_cap and len(losses) >= loss_cap:
            break
    return wins + losses
