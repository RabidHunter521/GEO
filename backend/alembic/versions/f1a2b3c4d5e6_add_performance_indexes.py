"""add_performance_indexes

Indexes on foreign keys and hot filter/order columns. Postgres does not
auto-index foreign keys, yet nearly every query filters by client_id / scan_id
and orders by a *_at column. (ai_traffic_snapshots(client_id, period) is already
covered by its UniqueConstraint, so it is omitted here.)

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, [columns])
_INDEXES = [
    ("ix_sqr_scan_id", "scan_query_results", ["scan_id"]),
    ("ix_sqr_scan_competitor", "scan_query_results", ["scan_id", "competitor_id"]),
    ("ix_sqr_created_at", "scan_query_results", ["created_at"]),
    ("ix_geo_scores_client_computed", "geo_scores", ["client_id", "computed_at"]),
    ("ix_scans_client_triggered", "scans", ["client_id", "triggered_at"]),
    ("ix_scans_client_status_completed", "scans", ["client_id", "status", "completed_at"]),
    ("ix_competitors_client", "competitors", ["client_id"]),
    ("ix_activity_client_event_created", "activity_log", ["client_id", "event_type", "created_at"]),
    ("ix_reports_client_period", "reports", ["client_id", "period_end"]),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
