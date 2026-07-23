"""add authority assets and client phone

Revision ID: dd8483cfad4a
Revises: 53304d0628ae
Create Date: 2026-07-23 21:09:07.254510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'dd8483cfad4a'
down_revision: Union[str, None] = '53304d0628ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("phone", sa.String(length=64), nullable=True))

    op.create_table(
        "authority_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("asset_key", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="missing"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("provenance_domain", sa.String(length=255), nullable=True),
        sa.Column("review_snapshots", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("found_nap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("nap_mismatch", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authority_assets_client_id", "authority_assets", ["client_id"])
    op.create_index(
        "uq_authority_assets_client_key", "authority_assets", ["client_id", "asset_key"],
        unique=True, postgresql_where=sa.text("asset_key IS NOT NULL"),
    )
    op.execute("ALTER TABLE authority_assets ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE authority_assets DISABLE ROW LEVEL SECURITY;")
    op.drop_index("uq_authority_assets_client_key", table_name="authority_assets")
    op.drop_index("ix_authority_assets_client_id", table_name="authority_assets")
    op.drop_table("authority_assets")
    op.drop_column("clients", "phone")
