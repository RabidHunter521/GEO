"""Industry intelligence packs.

Importing this package registers every pack, so validation runs at process
start. Each pack appends one import below; `registry.registered_keys()` must
equal `INDUSTRY_PACK_KEYS`.
"""
from app.industry_packs import base, registry  # noqa: F401
from app.industry_packs import healthcare  # noqa: F401  (registers on import)
from app.industry_packs import fnb  # noqa: F401  (registers on import)
from app.industry_packs import local_services  # noqa: F401  (registers on import)
from app.industry_packs import education  # noqa: F401  (registers on import)
from app.industry_packs import b2b_services  # noqa: F401  (registers on import)
from app.industry_packs import property  # noqa: F401  (registers on import)
from app.industry_packs import ecommerce  # noqa: F401  (registers on import)
from app.industry_packs import hospitality  # noqa: F401  (registers on import)
from app.industry_packs import automotive  # noqa: F401  (registers on import)
from app.industry_packs import financial_services  # noqa: F401  (registers on import)

__all__ = [
    "base", "registry", "healthcare", "fnb", "local_services", "education", "b2b_services",
    "property", "ecommerce", "hospitality", "automotive", "financial_services",
]
