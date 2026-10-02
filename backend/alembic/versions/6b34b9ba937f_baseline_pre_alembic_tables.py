"""baseline: the six tables that predate the Alembic chain

clients, competitors, scans, geo_scores, scan_query_results and activity_log
were created before Alembic was introduced (the original first migration,
f4ebafcdcf4a, already references clients). With no migration creating them,
`alembic upgrade head` could not build a database from empty -- the CI
"migrations" job failed at the very first revision.

This revision creates them exactly as they stood before f4ebafcdcf4a: only the
original columns (every later column is added by its own migration),
TIMESTAMPTZ timestamps defaulting to now() (0ef658851600 converts them), and a
plain competitor FK (f7c4a9e2d6b1 makes it cascade). RLS is enabled inline,
matching production, where it was turned on outside Alembic.

On any database that already has these tables -- production, which is in any
case far past this revision -- upgrade() does nothing.

Revision ID: 6b34b9ba937f
Revises:
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6b34b9ba937f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("clients", "competitors", "scans", "geo_scores", "scan_query_results", "activity_log")


def _tstz(name: str, nullable: bool, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        postgresql.TIMESTAMP(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if default_now else None,
    )


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("clients"):
        return  # pre-Alembic schema already present (production)

    op.create_table(
        "clients",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("brand_authority_score", sa.Integer(), nullable=False),
        sa.Column("content_quality_score", sa.Integer(), nullable=False),
        sa.Column("technical_foundations_verified", sa.Boolean(), nullable=False),
        sa.Column("structured_data_verified", sa.Boolean(), nullable=False),
        sa.Column("score_drop_threshold", sa.Integer(), nullable=False),
        _tstz("created_at", nullable=False, default_now=True),
        _tstz("archived_at", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "competitors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        _tstz("triggered_at", nullable=False, default_now=True),
        _tstz("completed_at", nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "geo_scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("ai_citability", sa.Float(), nullable=False),
        sa.Column("brand_authority", sa.Float(), nullable=False),
        sa.Column("content_quality", sa.Float(), nullable=False),
        sa.Column("technical_foundations", sa.Float(), nullable=False),
        sa.Column("structured_data", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        _tstz("computed_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scan_query_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("brand_detected", sa.Boolean(), nullable=False),
        _tstz("created_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "activity_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        _tstz("created_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
