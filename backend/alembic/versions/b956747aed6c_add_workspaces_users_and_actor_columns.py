"""add workspaces users and actor columns

Team accounts (docs/superpowers/plans/2026-09-30-team-accounts.md):
- workspaces: one row today, "SeenBy" (DEFAULT_WORKSPACE_ID)
- users: admins with argon2 password, mandatory TOTP, one-time invite links
- clients.workspace_id: NOT NULL, backfilled to the default workspace
- actor columns: activity_log.actor_user_id, work_log_entries.
  published_by_user_id, reports.sent_by_user_id (NULL = system)

RLS enabled inline on both new tables (CLAUDE.md §8); the anon REVOKE is
guarded because the Railway database has no anon role.

Revision ID: b956747aed6c
Revises: b16c2c6690fe
Create Date: 2026-09-30 08:30:50.883292

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Literals, not imports from app.core.constants: a migration must keep doing
# exactly what it did when it first ran. Must equal DEFAULT_WORKSPACE_ID /
# DEFAULT_WORKSPACE_NAME there (asserted by tests/test_team_schema.py).
DEFAULT_WORKSPACE_ID = "a0000000-0000-4000-8000-000000000001"
DEFAULT_WORKSPACE_NAME = "SeenBy"


# revision identifiers, used by Alembic.
revision: str = 'b956747aed6c'
down_revision: Union[str, None] = 'b16c2c6690fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        f"INSERT INTO workspaces (id, name) "
        f"VALUES ('{DEFAULT_WORKSPACE_ID}', '{DEFAULT_WORKSPACE_NAME}')"
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
        sa.Column("totp_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("last_totp_step", sa.Integer(), nullable=True),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(), nullable=True),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('owner', 'staff')", name="ck_users_role"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("invite_token_hash", name="uq_users_invite_token_hash"),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])

    for table in ("workspaces", "users"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                EXECUTE 'REVOKE ALL ON TABLE {table} FROM anon';
              END IF;
            END $$;
        """)

    # Existing clients all belong to the default workspace.
    op.add_column(
        "clients",
        sa.Column(
            "workspace_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_WORKSPACE_ID}'::uuid"),
        ),
    )
    op.alter_column("clients", "workspace_id", server_default=None)
    op.create_foreign_key(
        "fk_clients_workspace_id", "clients", "workspaces", ["workspace_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_clients_workspace_id", "clients", ["workspace_id"])

    for table, column in (
        ("activity_log", "actor_user_id"),
        ("work_log_entries", "published_by_user_id"),
        ("reports", "sent_by_user_id"),
    ):
        op.add_column(table, sa.Column(column, sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_{column}", table, "users", [column], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    for table, column in (
        ("reports", "sent_by_user_id"),
        ("work_log_entries", "published_by_user_id"),
        ("activity_log", "actor_user_id"),
    ):
        op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
        op.drop_column(table, column)
    op.drop_index("ix_clients_workspace_id", table_name="clients")
    op.drop_constraint("fk_clients_workspace_id", "clients", type_="foreignkey")
    op.drop_column("clients", "workspace_id")
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_table("users")
    op.drop_table("workspaces")
