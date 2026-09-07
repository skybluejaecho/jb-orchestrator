"""schedule bounded automatic notification retries

Revision ID: 0031_notification_auto_retry
Revises: 0030_notification_attempts
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_notification_auto_retry"
down_revision: str | None = "0030_notification_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.add_column(sa.Column("failure_retryable", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("automatic_retry_limit", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
        batch_op.create_check_constraint(
            "notification_automatic_retry_limit",
            "automatic_retry_limit BETWEEN 0 AND 10",
        )
        batch_op.create_index("ix_notification_deliveries_next_attempt_at", ["next_attempt_at"])
    with op.batch_alter_table("notification_delivery_attempts") as batch_op:
        batch_op.drop_constraint("notification_attempt_trigger", type_="check")
        batch_op.create_check_constraint(
            "notification_attempt_trigger",
            "trigger IN ('initial', 'manual', 'automatic', 'lease_recovery')",
        )
        batch_op.add_column(sa.Column("failure_retryable", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notification_delivery_attempts") as batch_op:
        batch_op.drop_column("failure_retryable")
        batch_op.drop_constraint("notification_attempt_trigger", type_="check")
        batch_op.create_check_constraint(
            "notification_attempt_trigger",
            "trigger IN ('initial', 'manual', 'lease_recovery')",
        )
    with op.batch_alter_table("notification_deliveries") as batch_op:
        batch_op.drop_index("ix_notification_deliveries_next_attempt_at")
        batch_op.drop_constraint("notification_automatic_retry_limit", type_="check")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("automatic_retry_limit")
        batch_op.drop_column("failure_retryable")
