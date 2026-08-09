"""add_activity_created_at_index

The global dashboard feed reads activity_log across ALL clients ordered by
created_at. The existing composite ix_activity_client_event_created leads
with client_id, so it cannot provide that ordering. A plain btree on
created_at serves ORDER BY created_at DESC via backward index scan.

Revision ID: b4e8f2a6c9d1
Revises: e2b8d6a5f1c3
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b4e8f2a6c9d1'
down_revision: Union[str, None] = 'e2b8d6a5f1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_activity_created_at", "activity_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_created_at", table_name="activity_log")
