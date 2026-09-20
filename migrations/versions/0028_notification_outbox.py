"""add notification subscriptions and delivery outbox

Revision ID: 0028_notification_outbox
Revises: 0027_readiness_monitor
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_notification_outbox"
down_revision: str | None = "0027_readiness_monitor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("destination_ref", sa.String(length=255), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "provider_key",
            "destination_ref",
            name="uq_notification_subscription_destination",
        ),
    )
    op.create_index(
        "ix_notification_subscriptions_project_enabled",
        "notification_subscriptions",
        ["project_id", "enabled"],
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "worker.readiness_alerted",
                "worker.readiness_critical",
                "worker.readiness_resolved",
                name="notification_event_type",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("destination_ref", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "claimed",
                "succeeded",
                "failed",
                name="notification_delivery_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["worker_readiness_alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["notification_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint(
            "subscription_id",
            "event_id",
            name="uq_notification_delivery_subscription_event",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_project_status",
        "notification_deliveries",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_project_status", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(
        "ix_notification_subscriptions_project_enabled",
        table_name="notification_subscriptions",
    )
    op.drop_table("notification_subscriptions")
