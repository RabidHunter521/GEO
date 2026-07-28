"""revoke anon/authenticated grants and stop auto-granting on new tables

Supabase creates `anon` and `authenticated` roles and, by default, grants them
full DML — SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER — on
every table in `public`, plus a default ACL that repeats those grants on every
table created afterwards.

SeenBy never uses them. There is no Supabase client, no anon key, no PostgREST
call and no Supabase Auth anywhere in the codebase; the API connects as
`postgres` over the session pooler. The grants are pure inherited default.

Why this is worth a migration rather than a shrug:

1. RLS is enabled on every table with ZERO policies, which is what actually
   blocks these roles today. The entire protection therefore rests on RLS
   staying enabled on every table forever — one `DISABLE ROW LEVEL SECURITY`,
   or one new table created without it, and the anon role has full read/write.
   The default ACL makes that second case the DEFAULT for new tables.
2. RLS does not apply to TRUNCATE at all — that is governed by the GRANT alone.
   Any path that can act as `anon` can therefore empty every table regardless
   of RLS.

Revoking makes the posture explicit and defence-in-depth rather than
single-layer. Reversible: downgrade restores the Supabase defaults.

Revision ID: d3f7a1c58e02
Revises: c7e4d1b90fa2
Create Date: 2026-07-28 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d3f7a1c58e02"
down_revision: Union[str, None] = "c7e4d1b90fa2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The roles are Supabase-specific: a local Postgres, a CI service container or
# a self-hosted deploy will not have them, and referencing a missing role is a
# hard error. Every statement is therefore guarded on the role existing.
_ROLES = ("anon", "authenticated")


def _for_each_existing_role(sql_template: str) -> None:
    for role in _ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                {sql_template.format(role=role)}
              END IF;
            END $$;
            """
        )


def upgrade() -> None:
    _for_each_existing_role(
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};"
        "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};"
        "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {role};"
        "REVOKE ALL ON SCHEMA public FROM {role};"
        # Stops the default ACL re-granting everything on the next CREATE TABLE.
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role};"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role};"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM {role};"
    )


def downgrade() -> None:
    """Restore the Supabase defaults.

    Only meaningful if something later starts using PostgREST or Supabase Auth;
    it re-opens the exposure described above, so do not run it to "fix" an
    unrelated permissions error.
    """
    _for_each_existing_role(
        "GRANT USAGE ON SCHEMA public TO {role};"
        "GRANT ALL ON ALL TABLES IN SCHEMA public TO {role};"
        "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role};"
        "GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO {role};"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role};"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {role};"
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO {role};"
    )
