"""add durable worker task leases

Revision ID: 0004_task_leases
Revises: 0003_workflows
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_task_leases"
down_revision: str | None = "0003_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add lease ownership and expiry fields to node executions."""

    op.add_column("node_executions", sa.Column("worker_id", sa.String(length=255)))
    op.add_column("node_executions", sa.Column("lease_token", sa.Uuid()))
    op.add_column("node_executions", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_node_executions_lease_expiry",
        "node_executions",
        ["status", "lease_expires_at"],
        postgresql_where=sa.text("lease_expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove worker task lease fields."""

    op.drop_index("ix_node_executions_lease_expiry", table_name="node_executions")
    op.drop_column("node_executions", "lease_expires_at")
    op.drop_column("node_executions", "lease_token")
    op.drop_column("node_executions", "worker_id")
