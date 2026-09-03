"""add idempotent request dispatch receipts

Revision ID: 0014_dispatch_receipts
Revises: 0013_workflow_bindings
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_dispatch_receipts"
down_revision: str | None = "0013_workflow_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create atomic project-scoped dispatch claims and results."""

    op.create_table(
        "request_dispatch_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload_digest", sa.String(length=71), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_execution_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(request_id IS NULL AND run_id IS NULL AND workflow_execution_id IS NULL "
            "AND completed_at IS NULL) OR "
            "(request_id IS NOT NULL AND run_id IS NOT NULL "
            "AND workflow_execution_id IS NOT NULL AND completed_at IS NOT NULL)",
            name="dispatch_receipt_result_all_or_none",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_dispatch_receipt_project", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["user_requests.id"],
            name="fk_dispatch_receipt_request",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_dispatch_receipt_run", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_dispatch_receipt_workflow",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_request_dispatch_receipts"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key", name="uq_dispatch_receipts_project_key"
        ),
    )


def downgrade() -> None:
    """Drop idempotent request dispatch receipts."""

    op.drop_table("request_dispatch_receipts")
