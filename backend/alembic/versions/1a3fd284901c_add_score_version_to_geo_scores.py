"""add score_version to geo_scores

Persists the scoring formula version (constants.SCORE_VERSION) on every
GeoScore row so a historical score can be attributed to the formula that
produced it.

Deliberately NOT backfilled. Existing rows were computed under an unknown
mix of v1.0.0-v1.4.0 and nothing in the schema records which; writing the
current version onto them would fabricate provenance and make a
methodology-driven score change indistinguishable from a market movement --
the exact failure this column exists to prevent. NULL means "unknown", and
consumers treat unknown as "not comparable", never as "same as current".

geo_scores already has RLS enabled (it is an existing table); adding a
column does not change that.

Revision ID: 1a3fd284901c
Revises: b4e8f2a6c9d1
Create Date: 2026-09-04 09:35:05.135024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a3fd284901c'
down_revision: Union[str, None] = 'b4e8f2a6c9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "geo_scores",
        sa.Column("score_version", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("geo_scores", "score_version")
