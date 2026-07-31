"""preserve outcome action evidence

Revision ID: b9e1f2a3c4d5
Revises: a8d4f2c1b7e9
Create Date: 2026-07-31 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b9e1f2a3c4d5"
down_revision: Union[str, None] = "a8d4f2c1b7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Databases that ran the original revision retain VARCHAR(32); fresh
    # databases already use JSONB after the historical migration was corrected.
    # `to_jsonb` preserves legacy text without attempting unsafe JSON parsing.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'outcome_actions'
              AND column_name = 'verification_result'
              AND data_type <> 'jsonb'
          ) THEN
            ALTER TABLE outcome_actions
            ALTER COLUMN verification_result TYPE JSONB
            USING to_jsonb(verification_result);
          END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE outcome_actions "
        "ADD COLUMN IF NOT EXISTS approval_evidence_hash VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE outcome_actions DROP COLUMN IF EXISTS approval_evidence_hash")
