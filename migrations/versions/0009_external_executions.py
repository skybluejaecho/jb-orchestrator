"""add durable external execution mappings

Revision ID: 0009_external_executions
Revises: 0008_budget_ledger
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_external_executions"
down_revision: str | None = "0008_budget_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create retry-safe mappings from JB tasks to external runs."""

    op.create_table(
        "external_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("executor_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("external_session_key", sa.String(length=512), nullable=False),
        sa.Column("external_agent_id", sa.String(length=255), nullable=True),
        sa.Column("external_run_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("terminal_result", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('starting', 'active', 'succeeded', 'failed', 'cancelled')",
            name="external_execution_status",
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_external_executions"),
        sa.UniqueConstraint("idempotency_key", name="uq_external_executions_idempotency_key"),
        sa.UniqueConstraint(
            "executor_key", "external_run_id", name="uq_external_executions_executor_run"
        ),
    )
    op.create_index("ix_external_executions_execution_id", "external_executions", ["execution_id"])
    op.create_index("ix_external_executions_run_id", "external_executions", ["run_id"])
    op.create_index(
        "ix_external_executions_status_updated", "external_executions", ["status", "updated_at"]
    )


def downgrade() -> None:
    """Drop external execution mappings."""

    op.drop_index("ix_external_executions_status_updated", table_name="external_executions")
    op.drop_index("ix_external_executions_run_id", table_name="external_executions")
    op.drop_index("ix_external_executions_execution_id", table_name="external_executions")
    op.drop_table("external_executions")
