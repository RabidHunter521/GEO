"""add toolkit_files table

Revision ID: f4ebafcdcf4a
Revises: 
Create Date: 2026-05-29 11:37:03.132733

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4ebafcdcf4a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('toolkit_files',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('llms_txt', sa.Text(), nullable=False),
        sa.Column('schema_json', sa.Text(), nullable=False),
        sa.Column('robots_txt', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('llms_verified', sa.Boolean(), nullable=False),
        sa.Column('schema_verified', sa.Boolean(), nullable=False),
        sa.Column('robots_verified', sa.Boolean(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', name='uq_toolkit_files_client_id')
    )


def downgrade() -> None:
    op.drop_table('toolkit_files')
