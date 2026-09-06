"""add durable worker readiness alerts

Revision ID: 0026_worker_alerts
Revises: 0025_worker_presence
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_worker_alerts"
down_revision: str | None = "0025_worker_presence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_readiness_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("executor_key", sa.String(length=128), nullable=False),
        sa.Column("ready_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "no_capable_worker",
                "capable_workers_offline",
                name="worker_readiness_issue_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "resolved",
                name="worker_readiness_alert_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"], ["workflow_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_execution_id",
            "node_key",
            "ready_since",
            name="uq_worker_readiness_alert_occurrence",
        ),
    )
    op.create_index(
        "ix_worker_readiness_alert_project_status",
        "worker_readiness_alerts",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_readiness_alert_project_status", table_name="worker_readiness_alerts")
    op.drop_table("worker_readiness_alerts")
