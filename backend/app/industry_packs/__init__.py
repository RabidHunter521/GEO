"""Industry intelligence packs.

Importing this package registers every pack, so validation runs at process
start. Tasks 3-5 each append one import below; `registry.registered_keys()`
must eventually equal `INDUSTRY_PACK_KEYS`.
"""
from app.industry_packs import base, registry  # noqa: F401
from app.industry_packs import healthcare  # noqa: F401  (registers on import)
from app.industry_packs import fnb  # noqa: F401  (registers on import)

__all__ = ["base", "registry", "healthcare", "fnb"]
