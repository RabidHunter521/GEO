"""Team management (owner only): list, invite, reset, deactivate admins.

Everything is scoped to the caller's workspace. The system caller (legacy
single-admin login) acts in the default workspace.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import request_identity
from app.core.auth import require_owner
from app.core.constants import DEFAULT_WORKSPACE_ID
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserListItem
from app.services import user_service
from app.services.user_invite_email import link_url, send_invite_email

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_owner)])


class InviteRequest(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=1, max_length=255)
    role: str = "staff"


class RoleChange(BaseModel):
    role: str


class LinkIssued(BaseModel):
    user: UserListItem
    link: str
    emailed: bool


def _caller(db: Session) -> User | None:
    uid = request_identity.current_user_id()
    return db.get(User, uid) if uid else None


def _workspace_id(db: Session) -> uuid.UUID:
    caller = _caller(db)
    return caller.workspace_id if caller else uuid.UUID(DEFAULT_WORKSPACE_ID)


def _status(user: User) -> str:
    if not user.is_active:
        return "deactivated"
    return "active" if user_service.is_usable(user) else "invited"


def _item(user: User) -> UserListItem:
    return UserListItem(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        workspace_id=user.workspace_id,
        is_active=user.is_active,
        status=_status(user),
        last_login_at=user.last_login_at,
        invite_expires_at=user.invite_expires_at if _status(user) == "invited" else None,
        created_at=user.created_at,
    )


def _get_in_workspace(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    # Uniform 404 for another workspace's user: never confirm it exists.
    if user is None or user.workspace_id != _workspace_id(db):
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=list[UserListItem])
def list_users(db: Session = Depends(get_db)):
    users = (
        db.query(User)
        .filter(User.workspace_id == _workspace_id(db))
        .order_by(User.is_active.desc(), User.created_at)
        .all()
    )
    return [_item(u) for u in users]


@router.post("/invite", response_model=LinkIssued, status_code=201)
def invite(body: InviteRequest, db: Session = Depends(get_db)):
    caller = _caller(db)
    try:
        user, raw = user_service.create_invite(
            db,
            workspace_id=_workspace_id(db),
            email=body.email,
            name=body.name,
            role=body.role,
            invited_by=caller,
        )
    except user_service.UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    emailed = send_invite_email(user, raw, invited_by=caller.name if caller else None)
    return LinkIssued(user=_item(user), link=link_url(raw), emailed=emailed)


@router.post("/{user_id}/reset", response_model=LinkIssued)
def reset(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """New one-time link: resends a pending invite, or makes an existing
    admin choose a new password and re-connect 2FA (e.g. a lost phone)."""
    user = _get_in_workspace(db, user_id)
    if not user.is_active:
        raise HTTPException(status_code=409, detail="Reactivate this admin first")
    was_set_up = user_service.is_usable(user)
    raw = user_service.issue_reset(db, user)
    emailed = send_invite_email(user, raw, is_reset=was_set_up)
    return LinkIssued(user=_item(user), link=link_url(raw), emailed=emailed)


def _set_active(db: Session, user_id: uuid.UUID, active: bool) -> UserListItem:
    user = _get_in_workspace(db, user_id)
    if not active:
        if user.id == request_identity.current_user_id():
            raise HTTPException(status_code=409, detail="You can't deactivate your own account")
        if user.role == "owner":
            if _other_active_owners(db, user) == 0:
                raise HTTPException(status_code=409, detail="The workspace must keep at least one owner")
    user_service.set_active(db, user, active)
    return _item(user)


@router.post("/{user_id}/deactivate", response_model=UserListItem)
def deactivate(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return _set_active(db, user_id, False)


@router.post("/{user_id}/activate", response_model=UserListItem)
def activate(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return _set_active(db, user_id, True)


def _other_active_owners(db: Session, user: User) -> int:
    return (
        db.query(User)
        .filter(
            User.workspace_id == user.workspace_id,
            User.role == "owner",
            User.is_active.is_(True),
            User.id != user.id,
        )
        .count()
    )


@router.patch("/{user_id}/role", response_model=UserListItem)
def change_role(user_id: uuid.UUID, body: RoleChange, db: Session = Depends(get_db)):
    """Works for active, invited and deactivated admins. A pending invite's
    link stays valid; a signed-in admin gets the new role on their next
    request (the role is read from the database every time)."""
    user = _get_in_workspace(db, user_id)
    if user.id == request_identity.current_user_id():
        raise HTTPException(status_code=409, detail="You can't change your own role")
    if user.role == "owner" and body.role != "owner" and user.is_active and _other_active_owners(db, user) == 0:
        raise HTTPException(status_code=409, detail="The workspace must keep at least one owner")
    try:
        user_service.change_role(db, user, body.role)
    except user_service.UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _item(user)


@router.delete("/{user_id}", status_code=204)
def delete(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = _get_in_workspace(db, user_id)
    if user.id == request_identity.current_user_id():
        raise HTTPException(status_code=409, detail="You can't delete your own account")
    try:
        user_service.delete_user(db, user)
    except user_service.UserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
