"""add legal name and registration number to clients

Optional, admin-only legal identity for each client (SSM). clients already
has RLS enabled; adding columns does not change that.

Revision ID: b16c2c6690fe
Revises: 283e6ea1f8c7
Create Date: 2026-09-30 07:22:01.500593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b16c2c6690fe'
down_revision: Union[str, None] = '283e6ea1f8c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("legal_name", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("registration_number", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "registration_number")
    op.drop_column("clients", "legal_name")
