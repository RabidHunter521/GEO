"""Brand aliases on clients and competitors

AI answers often name a brand differently from how it is stored ("Razorpay
Curlec" vs "Curlec", or a competitor's pre-rebrand name). brand_aliases lists
the other names that count as the same brand when deciding Seen by AI.

Plain JSON like clients.enabled_platforms; existing rows get []. No new table,
so no RLS statement is needed.

Revision ID: c621a0366980
Revises: a9734d89d193
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c621a0366980'
down_revision: Union[str, None] = 'a9734d89d193'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('clients', 'competitors'):
        op.add_column(
            table,
            sa.Column('brand_aliases', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )


def downgrade() -> None:
    for table in ('competitors', 'clients'):
        op.drop_column(table, 'brand_aliases')
