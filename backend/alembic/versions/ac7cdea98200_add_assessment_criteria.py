"""Assessment criteria: the points checklist behind each reviewed score

SCORE_VERSION v1.6.0 scores Brand Authority and Content Quality on a fixed
checklist (ASSESSMENT_RUBRICS). Each assessment stores its criteria with the
suggested and the reviewed points. Nullable: rows written before the checklist
have none and are flagged for re-review.

No new table, so no RLS statement is needed.

Revision ID: ac7cdea98200
Revises: b35b97dc4d0f
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ac7cdea98200'
down_revision: Union[str, None] = 'b35b97dc4d0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dimension_assessments', sa.Column('criteria', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('dimension_assessments', 'criteria')
