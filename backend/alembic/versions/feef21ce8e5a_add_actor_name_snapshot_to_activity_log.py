"""add actor_name snapshot to activity_log

Keeps "by <name>" on past activity after an admin account is deleted
(actor_user_id is ON DELETE SET NULL). Backfilled from users for rows
written since b956747aed6c. activity_log already has RLS enabled.

Revision ID: feef21ce8e5a
Revises: b956747aed6c
Create Date: 2026-10-01 10:22:54.824935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feef21ce8e5a'
down_revision: Union[str, None] = 'b956747aed6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("activity_log", sa.Column("actor_name", sa.String(length=255), nullable=True))
    op.execute(
        "UPDATE activity_log SET actor_name = users.name "
        "FROM users WHERE activity_log.actor_user_id = users.id"
    )


def downgrade() -> None:
    op.drop_column("activity_log", "actor_name")
