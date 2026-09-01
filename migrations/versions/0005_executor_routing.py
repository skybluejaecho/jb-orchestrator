"""add executor routing key to node executions

Revision ID: 0005_executor_routing
Revises: 0004_task_leases
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_executor_routing"
down_revision: str | None = "0004_task_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the executor selected by each immutable workflow snapshot."""

    op.add_column(
        "node_executions",
        sa.Column("executor_key", sa.String(length=128), nullable=True),
    )
    op.execute("UPDATE node_executions SET executor_key = 'default'")
    op.alter_column("node_executions", "executor_key", nullable=False)
    op.create_index(
        "ix_node_executions_executor_ready",
        "node_executions",
        ["executor_key", "status", "updated_at"],
    )


def downgrade() -> None:
    """Remove persisted executor routing."""

    op.drop_index("ix_node_executions_executor_ready", table_name="node_executions")
    op.drop_column("node_executions", "executor_key")
