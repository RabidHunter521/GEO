import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)
    code: str = Field(default="", max_length=16)


class UserPublic(BaseModel):
    """What the frontend session needs. Never includes secrets or hashes."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    workspace_id: uuid.UUID

    model_config = {"from_attributes": True}


class LinkInfo(BaseModel):
    email: str
    name: str
    is_reset: bool
    totp_secret: str
    otpauth_uri: str


class LinkAcceptRequest(BaseModel):
    password: str = Field(max_length=256)
    code: str = Field(max_length=16)


class UserListItem(UserPublic):
    is_active: bool
    status: str  # "active" | "invited" | "deactivated"
    last_login_at: datetime | None
    invite_expires_at: datetime | None
    created_at: datetime
