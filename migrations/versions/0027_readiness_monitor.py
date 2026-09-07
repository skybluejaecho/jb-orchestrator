"""add readiness monitor state

Revision ID: 0027_readiness_monitor
Revises: 0026_worker_alerts
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_readiness_monitor"
down_revision: str | None = "0026_worker_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("worker_instances") as batch_op:
        batch_op.drop_constraint("worker_kind", type_="check")
        batch_op.create_check_constraint(
            "worker_kind",
            "kind IN ('execution', 'workspace', 'scm', 'readiness_monitor')",
        )
    op.add_column(
        "worker_readiness_alerts",
        sa.Column("critical_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("worker_readiness_alerts", "critical_at")
    with op.batch_alter_table("worker_instances") as batch_op:
        batch_op.drop_constraint("worker_kind", type_="check")
        batch_op.create_check_constraint(
            "worker_kind",
            "kind IN ('execution', 'workspace', 'scm')",
        )
