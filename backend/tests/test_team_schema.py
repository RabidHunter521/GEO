"""Team-accounts schema: workspaces, users, and actor columns."""
import re
import uuid
from pathlib import Path

from app.core.constants import DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.report import Report
from app.models.user import USER_ROLES, User
from app.models.work_log_entry import WorkLogEntry
from app.models.workspace import Workspace

MIGRATION = next(
    (Path(__file__).resolve().parent.parent / "alembic" / "versions").glob(
        "*_add_workspaces_users_and_actor_columns.py"
    )
)


def test_migration_literals_match_constants():
    src = MIGRATION.read_text()
    assert re.search(rf'DEFAULT_WORKSPACE_ID = "{DEFAULT_WORKSPACE_ID}"', src)
    assert re.search(rf'DEFAULT_WORKSPACE_NAME = "{DEFAULT_WORKSPACE_NAME}"', src)
    assert "ENABLE ROW LEVEL SECURITY" in src
    # Guarded: a bare REVOKE ... FROM anon breaks boot on Railway (CLAUDE.md §8).
    assert "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')" in src


def test_new_client_lands_in_default_workspace(db):
    c = Client(name="Acme", website="https://acme.my", industry="Dental")
    db.add(c)
    db.commit()
    assert c.workspace_id == uuid.UUID(DEFAULT_WORKSPACE_ID)


def test_user_defaults(db):
    ws = db.get(Workspace, uuid.UUID(DEFAULT_WORKSPACE_ID))
    assert ws is not None and ws.name == DEFAULT_WORKSPACE_NAME
    u = User(workspace_id=ws.id, email="staff@seenby.my", name="Staff")
    db.add(u)
    db.commit()
    assert u.role == "staff" and u.role in USER_ROLES
    assert u.is_active is True
    assert u.failed_logins == 0
    assert u.password_hash is None and u.totp_confirmed_at is None


def test_actor_columns_exist():
    assert "actor_user_id" in ActivityLog.__table__.c
    assert "published_by_user_id" in WorkLogEntry.__table__.c
    assert "sent_by_user_id" in Report.__table__.c
