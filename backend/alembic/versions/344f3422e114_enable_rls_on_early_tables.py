"""enable RLS on the tables early migrations created without it

Ten tables created before the "RLS inline in every migration" rule
(CLAUDE.md §8) had RLS turned on outside Alembic on production. A database
built purely from the chain -- CI, a new environment -- therefore lacked it,
and CI's "every table must have RLS" gate failed. This makes the chain
self-sufficient.

ENABLE ROW LEVEL SECURITY is a no-op on a table that already has it, so on
production (38/38 tables enabled, verified 2026-07-28) this changes nothing.

Revision ID: 344f3422e114
Revises: c16b4d2148c2
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '344f3422e114'
down_revision: Union[str, None] = 'c16b4d2148c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "toolkit_files",
    "reports",
    "content_briefs",
    "content_analyses",
    "content_roadmaps",
    "ai_traffic_snapshots",
    "action_recommendations",
    "remediation_items",
    "dimension_assessments",
    "llm_call_logs",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Deliberately a no-op: on production these tables had RLS before this
    # revision existed, so disabling it on rollback would weaken production.
    pass
