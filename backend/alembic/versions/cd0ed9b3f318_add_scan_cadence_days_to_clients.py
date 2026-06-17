"""add scan_cadence_days to clients

Revision ID: cd0ed9b3f318
Revises: 4e1efb854b87
Create Date: 2026-06-16 15:29:17.270302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd0ed9b3f318'
down_revision: Union[str, None] = '4e1efb854b87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("scan_cadence_days", sa.Integer(), nullable=False, server_default="30"))


def downgrade() -> None:
    op.drop_column("clients", "scan_cadence_days")
