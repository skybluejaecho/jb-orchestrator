"""add notification delivery attempt ledger

Revision ID: 0030_notification_attempts
Revises: 0029_notification_worker
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_notification_attempts"
down_revision: str | None = "0029_notification_worker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.drop_constraint("notification_failure_code", type_="check")
        batch_op.create_check_constraint(
            "notification_failure_code",
            "failure_code IN ('provider_rejected', 'provider_unavailable', "
            "'timeout', 'lease_expired', 'unexpected')",
        )
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "trigger",
            sa.Enum(
                "initial",
                "manual",
                "lease_recovery",
                name="notification_attempt_trigger",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(255), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "claimed",
                "succeeded",
                "failed",
                name="notification_attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("result", sa.JSON()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "failure_code",
            sa.Enum(
                "provider_rejected",
                "provider_unavailable",
                "timeout",
                "lease_expired",
                "unexpected",
                name="notification_attempt_failure_code",
                native_enum=False,
                create_constraint=True,
            ),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_number > 0", name="ck_notification_attempt_number"),
        sa.ForeignKeyConstraint(
            ["delivery_id"], ["notification_deliveries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_notification_delivery_attempt_number",
        ),
    )
    op.create_index(
        "ix_notification_delivery_attempts_delivery",
        "notification_delivery_attempts",
        ["delivery_id", "attempt_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_delivery_attempts_delivery",
        table_name="notification_delivery_attempts",
    )
    op.drop_table("notification_delivery_attempts")
    op.execute(
        "UPDATE notification_deliveries SET failure_code = 'timeout' "
        "WHERE failure_code = 'lease_expired'"
    )
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.drop_constraint("notification_failure_code", type_="check")
        batch_op.create_check_constraint(
            "notification_failure_code",
            "failure_code IN "
            "('provider_rejected', 'provider_unavailable', 'timeout', 'unexpected')",
        )
