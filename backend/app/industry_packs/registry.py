"""Single lookup point for industry pack definitions.

Packs register themselves at import time (see `__init__`), and registration
validates, so an invalid pack breaks the process immediately rather than during
a scan. Definitions are returned by reference because they are frozen.

Lookups that the request path depends on — version stamping and subcategory
validation — DEGRADE for an unregistered key rather than raising, so the admin
API cannot 500 on a pack whose module has not landed yet. Task 5 adds the
assertion that all three supported keys really are registered, which is what
turns that graceful degradation back into a hard guarantee.
"""
from __future__ import annotations

from app.core.constants import INDUSTRY_PACK_KEYS
from app.industry_packs.base import IndustryPack, validate_pack

SUPPORTED_KEYS = INDUSTRY_PACK_KEYS

_PACKS: dict[str, IndustryPack] = {}


def register(pack: IndustryPack, _registry: dict[str, IndustryPack] | None = None) -> IndustryPack:
    """Validate and store a pack. `_registry` is an injection seam for tests."""
    store = _PACKS if _registry is None else _registry
    validate_pack(pack)
    if pack.key in store:
        raise ValueError(f"pack {pack.key!r} is already registered")
    store[pack.key] = pack
    return pack


def get_pack(key: str) -> IndustryPack:
    """Return the pack for `key`, or raise KeyError.

    Callers that must not fail on an unknown key should use the `*_for` helpers
    below instead of catching this.
    """
    try:
        return _PACKS[key]
    except KeyError:
        raise KeyError(
            f"no industry pack registered for {key!r}; registered: {sorted(_PACKS)}"
        ) from None


def find_pack(key: str | None) -> IndustryPack | None:
    """Return the pack for `key`, or None if there is not one.

    The safe counterpart to `get_pack`, for paths that must degrade rather than
    fail — a scan falls back to the legacy templates rather than dying because
    a pack module is missing.
    """
    if key is None:
        return None
    return _PACKS.get(key)


def registered_keys() -> tuple[str, ...]:
    return tuple(sorted(_PACKS))


def all_packs() -> tuple[IndustryPack, ...]:
    return tuple(_PACKS[key] for key in sorted(_PACKS))


def get_pack_version(key: str | None) -> str | None:
    """Version to stamp on a client selecting `key`. None when unknown."""
    if key is None:
        return None
    pack = _PACKS.get(key)
    return pack.version if pack else None


def subcategories_for(key: str | None) -> tuple[str, ...]:
    """Valid subcategories for `key`; empty when the pack is not registered.

    Empty means "cannot validate", so callers must treat it as "accept" rather
    than "reject everything" — otherwise an unlanded pack would block saves.
    """
    if key is None:
        return ()
    pack = _PACKS.get(key)
    return pack.subcategories if pack else ()
