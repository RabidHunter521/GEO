"""Who is making the current request.

Set by require_api_key for the duration of one API request:
- a signed user token  → that admin's User id
- the raw service key  → None ("system": the legacy single-admin login,
  the invite page, or any server-to-server call)
Celery tasks and scripts never set it, so they are also "system".

Read by anything that records an actor (e.g. ActivityLog), so call sites
don't have to pass the user around.
"""
import uuid
from contextvars import ContextVar

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)
_current_role: ContextVar[str | None] = ContextVar("current_role", default=None)


def set_current(user_id: uuid.UUID | None, role: str | None) -> None:
    _current_user_id.set(user_id)
    _current_role.set(role)


def current_user_id() -> uuid.UUID | None:
    return _current_user_id.get()


def is_owner_or_system() -> bool:
    """The owner, or the system caller (the legacy single-admin login)."""
    return current_role() in (None, "owner")


def current_role() -> str | None:
    """"owner" | "staff" for a signed-in admin; None for a system caller."""
    return _current_role.get()
