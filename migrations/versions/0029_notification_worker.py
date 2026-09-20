"""add notification delivery worker state

Revision ID: 0029_notification_worker
Revises: 0028_notification_outbox
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_notification_worker"
down_revision: str | None = "0028_notification_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification_deliveries", sa.Column("worker_id", sa.String(255)))
    op.add_column("notification_deliveries", sa.Column("lease_token", sa.Uuid()))
    op.add_column(
        "notification_deliveries", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column("notification_deliveries", sa.Column("result", sa.JSON()))
    op.add_column("notification_deliveries", sa.Column("failure_reason", sa.Text()))
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "failure_code",
            sa.Enum(
                "provider_rejected",
                "provider_unavailable",
                "timeout",
                "unexpected",
                name="notification_failure_code",
                native_enum=False,
                create_constraint=True,
            ),
        ),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("notification_deliveries", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_notification_delivery_attempt_count",
        "notification_deliveries",
        "attempt_count >= 0",
    )
    op.create_index(
        "ix_notification_deliveries_provider_claim",
        "notification_deliveries",
        ["provider_key", "status", "created_at"],
    )
    with op.batch_alter_table("worker_instances") as batch_op:
        batch_op.drop_constraint("worker_kind", type_="check")
        batch_op.create_check_constraint(
            "worker_kind",
            "kind IN ('execution', 'workspace', 'scm', 'readiness_monitor', 'notification')",
        )


def downgrade() -> None:
    op.execute("DELETE FROM worker_instances WHERE kind = 'notification'")
    with op.batch_alter_table("worker_instances") as batch_op:
        batch_op.drop_constraint("worker_kind", type_="check")
        batch_op.create_check_constraint(
            "worker_kind",
            "kind IN ('execution', 'workspace', 'scm', 'readiness_monitor')",
        )
    op.drop_index("ix_notification_deliveries_provider_claim", table_name="notification_deliveries")
    op.drop_constraint(
        "ck_notification_delivery_attempt_count", "notification_deliveries", type_="check"
    )
    op.drop_column("notification_deliveries", "completed_at")
    op.drop_column("notification_deliveries", "attempt_count")
    op.drop_column("notification_deliveries", "failure_code")
    op.drop_column("notification_deliveries", "failure_reason")
    op.drop_column("notification_deliveries", "result")
    op.drop_column("notification_deliveries", "lease_expires_at")
    op.drop_column("notification_deliveries", "lease_token")
    op.drop_column("notification_deliveries", "worker_id")
