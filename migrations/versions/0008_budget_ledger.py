"""add project budget reservation and usage ledger

Revision ID: 0008_budget_ledger
Revises: 0007_model_profiles
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_budget_ledger"
down_revision: str | None = "0007_model_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create budget balances, idempotent reservations, and usage records."""

    op.create_table(
        "budget_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("limit_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("spent_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("limit_usd >= 0", name="budget_limit_nonnegative"),
        sa.CheckConstraint("reserved_usd >= 0", name="budget_reserved_nonnegative"),
        sa.CheckConstraint("spent_usd >= 0", name="budget_spent_nonnegative"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_budget_accounts_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budget_accounts"),
        sa.UniqueConstraint("project_id", name="uq_budget_accounts_project_id"),
    )
    op.create_table(
        "budget_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actual_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'settled', 'forfeited', 'released')",
            name="budget_reservation_status",
        ),
        sa.CheckConstraint("reserved_usd >= 0", name="reservation_amount_nonnegative"),
        sa.CheckConstraint(
            "actual_usd IS NULL OR actual_usd >= 0",
            name="reservation_actual_nonnegative",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["budget_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_budget_reservations"),
        sa.UniqueConstraint("idempotency_key", name="uq_budget_reservations_idempotency_key"),
    )
    for column in ("account_id", "project_id", "run_id", "execution_id"):
        op.create_index(f"ix_budget_reservations_{column}", "budget_reservations", [column])
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("model_profile_key", sa.String(length=128), nullable=False),
        sa.Column("model_profile_version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('actual', 'estimated_forfeit')", name="usage_kind"),
        sa.CheckConstraint("input_tokens >= 0", name="usage_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="usage_output_tokens_nonnegative"),
        sa.CheckConstraint("cost_usd >= 0", name="usage_cost_nonnegative"),
        sa.ForeignKeyConstraint(["reservation_id"], ["budget_reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["budget_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
        sa.UniqueConstraint("reservation_id", name="uq_usage_records_reservation_id"),
    )
    for column in ("account_id", "project_id", "run_id", "execution_id"):
        op.create_index(f"ix_usage_records_{column}", "usage_records", [column])


def downgrade() -> None:
    """Drop usage accounting and budget balances."""

    for column in ("execution_id", "run_id", "project_id", "account_id"):
        op.drop_index(f"ix_usage_records_{column}", table_name="usage_records")
    op.drop_table("usage_records")
    for column in ("execution_id", "run_id", "project_id", "account_id"):
        op.drop_index(f"ix_budget_reservations_{column}", table_name="budget_reservations")
    op.drop_table("budget_reservations")
    op.drop_table("budget_accounts")
