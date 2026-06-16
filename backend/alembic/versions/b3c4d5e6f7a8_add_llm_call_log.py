"""add_llm_call_log

Revision ID: b3c4d5e6f7a8
Revises: f1a2b3c4d5e6
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_call_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'client_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('clients.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('service', sa.String(64), nullable=False),
        sa.Column('prompt_version', sa.String(16), nullable=False),
        sa.Column('model', sa.String(64), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=False),
        sa.Column(
            'called_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index('ix_llm_call_logs_client_id', 'llm_call_logs', ['client_id'])
    op.create_index('ix_llm_call_logs_called_at', 'llm_call_logs', ['called_at'])


def downgrade() -> None:
    op.drop_index('ix_llm_call_logs_called_at', table_name='llm_call_logs')
    op.drop_index('ix_llm_call_logs_client_id', table_name='llm_call_logs')
    op.drop_table('llm_call_logs')
