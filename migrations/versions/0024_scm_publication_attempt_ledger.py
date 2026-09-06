"""add durable SCM publication attempt ledger

Revision ID: 0024_scm_attempt_ledger
Revises: 0023_scm_bounded_auto_retry
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_scm_attempt_ledger"
down_revision: str | None = "0023_scm_bounded_auto_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scm_publication_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("publication_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "trigger",
            sa.Enum(
                "initial",
                "manual",
                "automatic",
                "lease_recovery",
                name="scm_publication_attempt_trigger",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "claimed",
                "succeeded",
                "failed",
                name="scm_publication_attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "failure_code",
            sa.Enum(
                "workspace_state",
                "provider_rejected",
                "provider_unavailable",
                "timeout",
                "result_mismatch",
                "unexpected",
                name="scm_publication_attempt_failure_code",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("failure_retryable", sa.Boolean(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        sa.ForeignKeyConstraint(["publication_id"], ["scm_publications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publication_id",
            "attempt_number",
            name="uq_scm_publication_attempts_number",
        ),
    )
    op.create_index(
        "ix_scm_publication_attempts_publication_id",
        "scm_publication_attempts",
        ["publication_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scm_publication_attempts_publication_id",
        table_name="scm_publication_attempts",
    )
    op.drop_table("scm_publication_attempts")
