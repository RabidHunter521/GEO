"""add industry intelligence pack selection to clients

Phase 4 stores only the pack SELECTION on the client. Every pack-specific
business fact lives in the shared Truth Vault, so the three packs specialize one
horizontal core instead of forking it — no pack-specific table exists or should.

Columns are plain varchar, deliberately not a PostgreSQL enum, so adding a
fourth pack later is a code change and not a migration.

Revision ID: c0f6b4e3d9a1
Revises: b9e5a3d2c8f0
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c0f6b4e3d9a1'
down_revision: Union[str, None] = 'b9e5a3d2c8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Conservative backfill of obvious industries only, per the Phase 4 plan.
#
# `~*` with \m...\M anchors each term to WORD boundaries rather than doing a
# substring match: "Biomedical Devices" must not become a healthcare client, and
# "Seafood Packaging" must not become F&B. Everything unmatched stays NULL and
# waits for admin review — a wrong pack silently changes which queries a client
# is scanned on, so guessing is worse than leaving it unset.
#
# Subcategory is NEVER guessed (the plan is explicit about this for local
# services, and the same reasoning holds for the other two packs), and
# industry_pack_version stays NULL because no registry version has actually
# produced evidence for these clients yet. NULL version therefore reads as
# "suggested from industry text, not yet reviewed", which is the truth.
_HEALTHCARE_TERMS = ('dental', 'dentist', 'clinic', 'hospital', 'medical', 'healthcare')
_FNB_TERMS = ('restaurant', 'cafe', 'bakery', 'catering')


def _word_match(terms: tuple[str, ...]) -> str:
    return '|'.join(rf'\m{term}\M' for term in terms)


def upgrade() -> None:
    op.add_column('clients', sa.Column('industry_pack', sa.String(length=32), nullable=True))
    op.add_column('clients', sa.Column('industry_subcategory', sa.String(length=64), nullable=True))
    op.add_column('clients', sa.Column('industry_pack_version', sa.String(length=16), nullable=True))

    # Idempotent: only ever fills a NULL, so a re-run can never overwrite an
    # admin's reviewed choice.
    op.execute(
        sa.text(
            "UPDATE clients SET industry_pack = 'healthcare' "
            "WHERE industry_pack IS NULL AND industry ~* :pattern"
        ).bindparams(pattern=_word_match(_HEALTHCARE_TERMS))
    )
    op.execute(
        sa.text(
            "UPDATE clients SET industry_pack = 'fnb' "
            "WHERE industry_pack IS NULL AND industry ~* :pattern"
        ).bindparams(pattern=_word_match(_FNB_TERMS))
    )


def downgrade() -> None:
    op.drop_column('clients', 'industry_pack_version')
    op.drop_column('clients', 'industry_subcategory')
    op.drop_column('clients', 'industry_pack')
