"""change scan_query_results.competitor_id FK from SET NULL to CASCADE

Edge case #38: deleting a competitor used to SET NULL its historical scan rows,
which then read as the client's own queries (competitor_id IS NULL) and inflated
the client's visibility frequency on every recompute-from-rows surface. CASCADE
deletes those competitor rows instead, so removing a competitor cleanly removes
its data rather than relabelling it.

Revision ID: f7c4a9e2d6b1
Revises: cd0ed9b3f318
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f7c4a9e2d6b1'
down_revision: Union[str, None] = 'cd0ed9b3f318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = 'scan_query_results_competitor_id_fkey'


def _drop_existing_competitor_fk() -> None:
    """Drop whatever FK currently sits on scan_query_results.competitor_id,
    discovering its real name so this works regardless of how it was named."""
    op.execute(
        """
        DO $$
        DECLARE cname text;
        BEGIN
            SELECT con.conname INTO cname
            FROM pg_constraint con
            JOIN pg_attribute att
              ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
            WHERE con.conrelid = 'scan_query_results'::regclass
              AND con.contype = 'f'
              AND att.attname = 'competitor_id';
            IF cname IS NOT NULL THEN
                EXECUTE 'ALTER TABLE scan_query_results DROP CONSTRAINT ' || quote_ident(cname);
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _drop_existing_competitor_fk()
    op.create_foreign_key(
        _FK_NAME,
        'scan_query_results',
        'competitors',
        ['competitor_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    _drop_existing_competitor_fk()
    op.create_foreign_key(
        _FK_NAME,
        'scan_query_results',
        'competitors',
        ['competitor_id'],
        ['id'],
        ondelete='SET NULL',
    )
