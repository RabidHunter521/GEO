"""merge search signals and conversion events

Task 5 (search_query_signals, e2b8d6f5a1c3) and Task 6 (conversion_events,
f3c9e7a2b4d5) were built in parallel off the same parent (d1a7c5f4e0b2),
creating two alembic heads. This empty merge migration reunifies them into a
single linear chain.

Revision ID: a4b5c6d7e8f9
Revises: e2b8d6f5a1c3, f3c9e7a2b4d5
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str]] = ("e2b8d6f5a1c3", "f3c9e7a2b4d5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
