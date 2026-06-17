"""add internal_notes to clients

Revision ID: 4e1efb854b87
Revises: b3c4d5e6f7a8
Create Date: 2026-06-16 15:14:57.093898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e1efb854b87'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("internal_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "internal_notes")
