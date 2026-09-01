"""add durable workflow definitions and executions

Revision ID: 0003_workflows
Revises: 0002_domain_events
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_workflows"
down_revision: str | None = "0002_domain_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create versioned workflow definitions and durable execution state."""

    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_definitions"),
        sa.UniqueConstraint("key", "version", name="uq_workflow_definitions_key_version"),
    )
    op.create_index("ix_workflow_definitions_key", "workflow_definitions", ["key"])

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'awaiting_approval', 'succeeded', "
            "'failed', 'cancelled')",
            name="workflow_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name="fk_workflow_executions_run_id_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_executions"),
        sa.UniqueConstraint("run_id", name="uq_workflow_executions_run_id"),
    )
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"])

    op.create_table(
        "node_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("visit_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'running', 'awaiting_approval', "
            "'succeeded', 'failed', 'cancelled')",
            name="node_execution_status",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('success', 'failure', 'approved', 'rejected')",
            name="node_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_node_executions_workflow_execution_id_workflow_executions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_node_executions"),
        sa.UniqueConstraint(
            "workflow_execution_id",
            "node_key",
            name="uq_node_executions_workflow_node",
        ),
    )
    op.create_index(
        "ix_node_executions_workflow_execution_id",
        "node_executions",
        ["workflow_execution_id"],
    )
    op.create_index(
        "ix_node_executions_status_updated",
        "node_executions",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    """Drop workflow execution and definition tables."""

    op.drop_index("ix_node_executions_status_updated", table_name="node_executions")
    op.drop_index("ix_node_executions_workflow_execution_id", table_name="node_executions")
    op.drop_table("node_executions")
    op.drop_index("ix_workflow_executions_status", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("ix_workflow_definitions_key", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
