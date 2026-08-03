"""add truth vault and locations

Revision ID: b9e5a3d2c8f0
Revises: b9e1f2a3c4d5
Create Date: 2026-08-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b9e5a3d2c8f0"
down_revision: Union[str, None] = "b9e1f2a3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_locations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("website", sa.String(length=1024), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=True),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("postcode", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("service_area_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("hours_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("booking_url", sa.String(length=1024), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "client_id", name="uq_business_locations_id_client"),
    )
    op.create_index(
        "uq_business_locations_client_slug", "business_locations", ["client_id", "slug"], unique=True
    )
    op.create_index(
        "uq_business_locations_primary_client",
        "business_locations",
        ["client_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE"),
    )
    op.create_index("ix_business_locations_client_active", "business_locations", ["client_id", "active"])

    op.create_table(
        "truth_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("fact_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id", "client_id"],
            ["business_locations.id", "business_locations.client_id"],
            name="fk_truth_facts_location_client",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_truth_fact_brand",
        "truth_facts",
        ["client_id", "fact_type", "fact_key"],
        unique=True,
        postgresql_where=sa.text("location_id IS NULL"),
    )
    op.create_index(
        "uq_truth_fact_location",
        "truth_facts",
        ["client_id", "location_id", "fact_type", "fact_key"],
        unique=True,
        postgresql_where=sa.text("location_id IS NOT NULL"),
    )
    op.create_index("ix_truth_facts_client_fact_type", "truth_facts", ["client_id", "fact_type"])
    op.create_index("ix_truth_facts_location", "truth_facts", ["location_id"])

    op.create_table(
        "truth_fact_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("truth_fact_id", sa.UUID(), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(), nullable=True),
        sa.Column("effective_to", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'retired')", name="ck_truth_fact_versions_status"
        ),
        sa.ForeignKeyConstraint(["truth_fact_id"], ["truth_facts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_truth_fact_versions_open_approved",
        "truth_fact_versions",
        ["truth_fact_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved' AND effective_to IS NULL"),
    )
    op.create_index(
        "ix_truth_fact_versions_fact_status", "truth_fact_versions", ["truth_fact_id", "status"]
    )
    op.create_index(
        "ix_truth_fact_versions_effective",
        "truth_fact_versions",
        ["truth_fact_id", "effective_from", "effective_to"],
    )

    op.add_column("outcome_actions", sa.Column("location_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_outcome_actions_location_client",
        "outcome_actions",
        "business_locations",
        ["location_id", "client_id"],
        ["id", "client_id"],
        ondelete="SET NULL (location_id)",
    )
    op.create_index(
        "ix_outcome_actions_client_location_status",
        "outcome_actions",
        ["client_id", "location_id", "status"],
    )

    for table_name in ("business_locations", "truth_facts", "truth_fact_versions"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"REVOKE ALL ON TABLE {table_name} FROM anon;")
    op.execute(
        """
        CREATE FUNCTION prevent_truth_fact_version_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.status = 'draft'
               AND NEW.status = 'approved'
               AND OLD.approved_at IS NULL
               AND OLD.approved_by IS NULL
               AND NEW.approved_at IS NOT NULL
               AND NEW.approved_by IS NOT NULL
               AND NEW.effective_from IS NOT NULL
               AND OLD.effective_to IS NULL
               AND NEW.effective_to IS NULL
               AND NEW.id IS NOT DISTINCT FROM OLD.id
               AND NEW.truth_fact_id IS NOT DISTINCT FROM OLD.truth_fact_id
               AND NEW.value_json IS NOT DISTINCT FROM OLD.value_json
               AND NEW.source_url IS NOT DISTINCT FROM OLD.source_url
               AND NEW.reviewer_note IS NOT DISTINCT FROM OLD.reviewer_note
               AND NEW.effective_from IS NOT DISTINCT FROM OLD.effective_from
               AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
            THEN
                RETURN NEW;
            END IF;

            IF TG_OP = 'UPDATE'
               AND OLD.status = 'approved'
               AND NEW.status = 'approved'
               AND OLD.effective_from IS NOT NULL
               AND OLD.effective_to IS NULL
               AND NEW.effective_to IS NOT NULL
               AND NEW.effective_to >= OLD.effective_from
               AND NEW.id IS NOT DISTINCT FROM OLD.id
               AND NEW.truth_fact_id IS NOT DISTINCT FROM OLD.truth_fact_id
               AND NEW.value_json IS NOT DISTINCT FROM OLD.value_json
               AND NEW.source_url IS NOT DISTINCT FROM OLD.source_url
               AND NEW.reviewer_note IS NOT DISTINCT FROM OLD.reviewer_note
               AND NEW.effective_from IS NOT DISTINCT FROM OLD.effective_from
               AND NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at
               AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
               AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
            THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'truth fact versions are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_truth_fact_versions_append_only
        BEFORE UPDATE OR DELETE ON truth_fact_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_truth_fact_version_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_truth_fact_versions_append_only ON truth_fact_versions")
    op.execute("DROP FUNCTION prevent_truth_fact_version_mutation()")

    op.drop_index("ix_outcome_actions_client_location_status", table_name="outcome_actions")
    op.drop_constraint("fk_outcome_actions_location_client", "outcome_actions", type_="foreignkey")
    op.drop_column("outcome_actions", "location_id")

    for table_name in ("truth_fact_versions", "truth_facts", "business_locations"):
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_truth_fact_versions_effective", table_name="truth_fact_versions")
    op.drop_index("ix_truth_fact_versions_fact_status", table_name="truth_fact_versions")
    op.drop_index("uq_truth_fact_versions_open_approved", table_name="truth_fact_versions")
    op.drop_table("truth_fact_versions")

    op.drop_index("ix_truth_facts_location", table_name="truth_facts")
    op.drop_index("ix_truth_facts_client_fact_type", table_name="truth_facts")
    op.drop_index("uq_truth_fact_location", table_name="truth_facts")
    op.drop_index("uq_truth_fact_brand", table_name="truth_facts")
    op.drop_table("truth_facts")

    op.drop_index("ix_business_locations_client_active", table_name="business_locations")
    op.drop_index("uq_business_locations_primary_client", table_name="business_locations")
    op.drop_index("uq_business_locations_client_slug", table_name="business_locations")
    op.drop_table("business_locations")
