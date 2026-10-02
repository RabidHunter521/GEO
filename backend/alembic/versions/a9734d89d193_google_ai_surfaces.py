"""Google AI surfaces: answer_shown + both Google platforms on by default

Google AI Overviews / AI Mode (docs/superpowers/plans/2026-10-02-google-ai-surfaces.md).

- scan_query_results.answer_shown: NULL for every existing row (those
  surfaces always answer); False marks a Google search with no AI Overview.
- clients.enabled_platforms: the default gains google_aio + google_ai_mode,
  and every non-archived client gets both appended (switchable off per client
  in Settings). They are reported, not scored, so no score changes.

No new table, so no RLS statement is needed.

Revision ID: a9734d89d193
Revises: 5435ef02ede2
Create Date: 2026-10-02

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a9734d89d193'
down_revision: Union[str, None] = '5435ef02ede2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GOOGLE = ["google_aio", "google_ai_mode"]
_OLD_DEFAULT = '\'["chatgpt", "perplexity", "gemini", "claude"]\''
_NEW_DEFAULT = (
    '\'["chatgpt", "perplexity", "gemini", "claude", "google_aio", "google_ai_mode"]\''
)


def _rewrite_platforms(where: str, change) -> None:
    """Rewrite enabled_platforms row by row. The column is plain JSON, which
    has no array operators, and a client's list can be any subset."""
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, enabled_platforms FROM clients {where}")).fetchall()
    for row_id, platforms in rows:
        current = platforms if isinstance(platforms, list) else json.loads(platforms or "[]")
        updated = change(current)
        if updated != current:
            bind.execute(
                sa.text("UPDATE clients SET enabled_platforms = CAST(:p AS JSON) WHERE id = :id"),
                {"p": json.dumps(updated), "id": row_id},
            )


def upgrade() -> None:
    op.add_column('scan_query_results', sa.Column('answer_shown', sa.Boolean(), nullable=True))
    op.alter_column('clients', 'enabled_platforms', server_default=sa.text(_NEW_DEFAULT))
    _rewrite_platforms(
        "WHERE archived_at IS NULL",
        lambda current: current + [p for p in _GOOGLE if p not in current],
    )


def downgrade() -> None:
    _rewrite_platforms("", lambda current: [p for p in current if p not in _GOOGLE])
    op.alter_column('clients', 'enabled_platforms', server_default=sa.text(_OLD_DEFAULT))
    op.drop_column('scan_query_results', 'answer_shown')
