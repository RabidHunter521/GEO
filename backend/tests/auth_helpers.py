"""Signed-in admin credentials for API tests.

The `db` fixture (conftest.py) seeds TEST_OWNER, a fully set-up owner in the
default workspace. Admin routes accept only per-user tokens, so tests send
owner_headers() instead of the old shared key.
"""
import time
import uuid

import jwt

from app.core.auth import USER_TOKEN_AUDIENCE, user_token_key
from app.core.constants import DEFAULT_WORKSPACE_ID

TEST_OWNER_ID = uuid.UUID("b1111111-1111-4111-8111-111111111111")
TEST_OWNER_EMAIL = "test-owner@seenby.test"


def token_for(user_id: uuid.UUID, workspace_id: str = DEFAULT_WORKSPACE_ID, ttl: int = 300) -> str:
    now = int(time.time())
    claims = {"sub": str(user_id), "wid": str(workspace_id), "aud": USER_TOKEN_AUDIENCE, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, user_token_key(), algorithm="HS256")


def owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(TEST_OWNER_ID)}"}


def seed_test_owner(session) -> None:
    from datetime import datetime

    from app.models.user import User

    session.add(
        User(
            id=TEST_OWNER_ID,
            workspace_id=uuid.UUID(DEFAULT_WORKSPACE_ID),
            email=TEST_OWNER_EMAIL,
            name="Test Owner",
            role="owner",
            password_hash="unused-in-api-tests",
            totp_secret="JBSWY3DPEHPK3PXP",
            totp_confirmed_at=datetime(2026, 1, 1),
        )
    )
