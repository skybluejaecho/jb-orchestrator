"""add immutable task artifacts

Revision ID: 0011_task_artifacts
Revises: 0010_event_sequence
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_task_artifacts"
down_revision: str | None = "0010_event_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable per-node-visit task artifacts."""

    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("producer_node_key", sa.String(length=128), nullable=False),
        sa.Column("visit_count", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure')",
            name="task_artifact_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["workflow_executions.id"],
            name="fk_task_artifacts_execution_id_workflow_executions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_task_artifacts"),
        sa.UniqueConstraint(
            "execution_id",
            "producer_node_key",
            "visit_count",
            name="uq_task_artifacts_execution_node_visit",
        ),
    )
    op.create_index(
        "ix_task_artifacts_execution_created",
        "task_artifacts",
        ["execution_id", "created_at"],
    )


def downgrade() -> None:
    """Drop task artifacts."""

    op.drop_index("ix_task_artifacts_execution_created", table_name="task_artifacts")
    op.drop_table("task_artifacts")
