"""Who is making the current request.

Set by require_api_key for the duration of one API request:
- a signed user token → that admin's User id
Service routes (sign-in, invite links), Celery tasks and scripts never set
it: no current user = "System".

Read by anything that records an actor (e.g. ActivityLog), so call sites
don't have to pass the user around.
"""
import uuid
from contextvars import ContextVar

_current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)
_current_role: ContextVar[str | None] = ContextVar("current_role", default=None)
_current_name: ContextVar[str | None] = ContextVar("current_name", default=None)


def set_current(user_id: uuid.UUID | None, role: str | None, name: str | None = None) -> None:
    _current_user_id.set(user_id)
    _current_role.set(role)
    _current_name.set(name)


def current_name() -> str | None:
    return _current_name.get()


def current_user_id() -> uuid.UUID | None:
    return _current_user_id.get()


def is_owner() -> bool:
    return current_role() == "owner"


def current_role() -> str | None:
    """"owner" | "staff" for a signed-in admin; None outside an admin request."""
    return _current_role.get()
