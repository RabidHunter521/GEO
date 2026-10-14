"""Client custom questions: admin-written scan questions

For businesses no industry pack fits well, an admin can add up to
MAX_CUSTOM_QUESTIONS questions of their own; each is asked once per enabled
platform on every scan, alongside the generated questions. Stored as a JSON
list of {"text", "category"}; existing rows get [].

No new table, so no RLS statement is needed.

Revision ID: d2a30a2d5bf4
Revises: a25d2f2a60f5
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd2a30a2d5bf4'
down_revision: Union[str, None] = 'a25d2f2a60f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'clients',
        sa.Column('custom_questions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column('clients', 'custom_questions')
