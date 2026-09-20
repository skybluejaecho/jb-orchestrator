"""add durable worker process presence ledger

Revision ID: 0025_worker_presence
Revises: 0024_scm_attempt_ledger
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_worker_presence"
down_revision: str | None = "0024_scm_attempt_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_instances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "execution",
                "workspace",
                "scm",
                name="worker_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("workspace_scope", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "stopped",
                name="worker_lifecycle_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("process_id > 0", name="process_id_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_instances_worker_id", "worker_instances", ["worker_id"])
    op.create_index(
        "ix_worker_instances_status_seen",
        "worker_instances",
        ["status", "last_seen_at"],
    )
    op.create_index(
        "ix_worker_instances_kind_seen",
        "worker_instances",
        ["kind", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_instances_kind_seen", table_name="worker_instances")
    op.drop_index("ix_worker_instances_status_seen", table_name="worker_instances")
    op.drop_index("ix_worker_instances_worker_id", table_name="worker_instances")
    op.drop_table("worker_instances")
