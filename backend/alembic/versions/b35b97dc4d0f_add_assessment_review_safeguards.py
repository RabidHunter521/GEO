"""Assessment review safeguards: reviewer, adjustment reason, edited evidence

Brand Authority and Content Quality are Claude-suggested, admin-reviewed. The
review step now records who reviewed, requires a reason whenever the admin's
score or evidence differs from the suggestion, and keeps the evidence as the
admin edited it next to the original suggestion. All nullable: existing rows
predate the safeguards and stay as they are.

No new table, so no RLS statement is needed.

Revision ID: b35b97dc4d0f
Revises: d2a30a2d5bf4
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b35b97dc4d0f'
down_revision: Union[str, None] = 'd2a30a2d5bf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dimension_assessments', sa.Column('reviewed_by', sa.String(length=255), nullable=True))
    op.add_column('dimension_assessments', sa.Column('adjustment_reason', sa.Text(), nullable=True))
    op.add_column('dimension_assessments', sa.Column('final_bullets', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('dimension_assessments', 'final_bullets')
    op.drop_column('dimension_assessments', 'adjustment_reason')
    op.drop_column('dimension_assessments', 'reviewed_by')
