"""all-platform source capture columns

scan_query_results.sources_captured: whether the platform adapter parsed the
answer's sources (NULL for rows written before all-platform capture, whose
capture state is unknown).

share_of_source_snapshots.source_capture_version / source_platforms: which
capture method and platforms produced each snapshot, so a coverage change is
never read as movement. Existing snapshots are backfilled to "v1" /
["perplexity"] -- deterministic, because only Perplexity sources were captured
before this revision.

Both tables already have RLS enabled; no new table, no role grants.

Revision ID: c16b4d2148c2
Revises: feef21ce8e5a
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c16b4d2148c2'
down_revision: Union[str, None] = 'feef21ce8e5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scan_query_results", sa.Column("sources_captured", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "share_of_source_snapshots",
        sa.Column("source_capture_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "share_of_source_snapshots",
        sa.Column("source_platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        "UPDATE share_of_source_snapshots "
        "SET source_capture_version = 'v1', source_platforms = '[\"perplexity\"]'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("share_of_source_snapshots", "source_platforms")
    op.drop_column("share_of_source_snapshots", "source_capture_version")
    op.drop_column("scan_query_results", "sources_captured")
