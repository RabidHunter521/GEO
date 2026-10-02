"""add placement_targets

Placement engine (docs/superpowers/plans/2026-10-02-placement-engine.md): one
row per (client, page) AI answers draw on that does not name the client.

Revision ID: 5435ef02ede2
Revises: 7c2e9b4d1a60
Create Date: 2026-10-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5435ef02ede2'
down_revision: Union[str, None] = '7c2e9b4d1a60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_fk(name: str, target: str, ondelete: str, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
    )


def _jsonb_list(name: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"))


def upgrade() -> None:
    op.create_table(
        "placement_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid_fk("client_id", "clients.id", "CASCADE", nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("answers_count", sa.Integer(), nullable=False, server_default="0"),
        _jsonb_list("platforms"),
        _jsonb_list("query_categories"),
        _jsonb_list("competitors_present"),
        _uuid_fk("representative_result_id", "scan_query_results.id", "SET NULL"),
        sa.Column("other_businesses_listed", sa.Integer(), nullable=True),
        sa.Column("client_present", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority_score", sa.Integer(), nullable=False, server_default="0"),
        _jsonb_list("priority_reasons"),
        _uuid_fk("authority_asset_id", "authority_assets.id", "SET NULL"),
        _uuid_fk("outcome_action_id", "outcome_actions.id", "SET NULL"),
        sa.Column("page_analysis", postgresql.JSONB(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        _jsonb_list("outreach_drafts"),
        _uuid_fk("first_seen_scan_id", "scans.id", "SET NULL"),
        _uuid_fk("last_seen_scan_id", "scans.id", "SET NULL"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("scans_missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("placed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "url", name="uq_placement_targets_client_url"),
    )
    op.create_index("ix_placement_targets_client_id", "placement_targets", ["client_id"])
    # RLS inline, guarded anon revoke (CLAUDE.md §8).
    op.execute("ALTER TABLE placement_targets ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') "
        "THEN EXECUTE 'REVOKE ALL ON TABLE placement_targets FROM anon'; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_index("ix_placement_targets_client_id", table_name="placement_targets")
    op.drop_table("placement_targets")
