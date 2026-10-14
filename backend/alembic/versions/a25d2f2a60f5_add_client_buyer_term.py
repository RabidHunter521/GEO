"""Client buyer term: what buyers call the business

`clients.industry` is a broad picklist category ("Finance"), and scan
questions read "Best {industry} in ...". buyer_term ("payment gateway")
fills {industry} when set. Nullable: NULL keeps the old behaviour, so no
existing client's questions change until an admin fills it in.

No new table, so no RLS statement is needed.

Revision ID: a25d2f2a60f5
Revises: c621a0366980
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a25d2f2a60f5'
down_revision: Union[str, None] = 'c621a0366980'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('buyer_term', sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'buyer_term')
