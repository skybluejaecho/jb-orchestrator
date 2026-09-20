"""add durable SCM publication ledger

Revision ID: 0020_scm_publications
Revises: 0019_workspace_operations
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_scm_publications"
down_revision: str | None = "0019_workspace_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scm_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_execution_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("repository", sa.String(length=2048), nullable=False),
        sa.Column("source_branch", sa.String(length=255), nullable=False),
        sa.Column("target_branch", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            name="uq_scm_publications_execution_key",
        ),
    )
    op.create_check_constraint(
        "scm_publication_status",
        "scm_publications",
        "status IN ('pending', 'claimed', 'succeeded', 'failed')",
    )
    op.create_index(
        "ix_scm_publications_external_execution_id",
        "scm_publications",
        ["external_execution_id"],
    )
    op.create_index(
        "ix_scm_publications_claim",
        "scm_publications",
        ["provider_key", "workspace_scope", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("scm_publications")
