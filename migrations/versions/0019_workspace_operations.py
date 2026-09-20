"""add durable workspace operation queue

Revision ID: 0019_workspace_operations
Revises: 0018_workspace_lifecycle
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_workspace_operations"
down_revision: str | None = "0018_workspace_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_executions",
        sa.Column("workspace_scope", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_external_executions_workspace_scope",
        "external_executions",
        ["workspace_scope"],
    )
    op.create_table(
        "workspace_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_execution_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=7), nullable=False),
        sa.Column("target_ref", sa.String(length=255), nullable=False),
        sa.Column("workspace_scope", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["external_execution_id"], ["external_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_execution_id",
            "idempotency_key",
            name="uq_workspace_operations_execution_key",
        ),
    )
    op.create_check_constraint(
        "workspace_operation_kind",
        "workspace_operations",
        "kind IN ('inspect', 'cleanup')",
    )
    op.create_check_constraint(
        "workspace_operation_status",
        "workspace_operations",
        "status IN ('pending', 'claimed', 'succeeded', 'failed')",
    )
    op.create_index(
        "ix_workspace_operations_external_execution_id",
        "workspace_operations",
        ["external_execution_id"],
    )
    op.create_index(
        "ix_workspace_operations_claim",
        "workspace_operations",
        ["workspace_scope", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("workspace_operations")
    op.drop_index("ix_external_executions_workspace_scope", table_name="external_executions")
    op.drop_column("external_executions", "workspace_scope")
