"""add transport-neutral request origins

Revision ID: 0015_request_origins
Revises: 0014_dispatch_receipts
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_request_origins"
down_revision: str | None = "0014_dispatch_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store request provenance and namespace dispatch keys by ingress."""

    op.add_column(
        "request_dispatch_receipts",
        sa.Column("ingress_key", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE request_dispatch_receipts SET ingress_key = 'legacy' WHERE ingress_key IS NULL"
        )
    )
    op.alter_column("request_dispatch_receipts", "ingress_key", nullable=False)
    op.drop_constraint(
        "uq_dispatch_receipts_project_key",
        "request_dispatch_receipts",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_dispatch_receipts_project_ingress_key",
        "request_dispatch_receipts",
        ["project_id", "ingress_key", "idempotency_key"],
    )

    op.add_column("user_requests", sa.Column("ingress_key", sa.String(length=64)))
    op.add_column("user_requests", sa.Column("external_request_id", sa.String(length=255)))
    op.add_column("user_requests", sa.Column("origin_actor_id", sa.String(length=255)))
    op.add_column("user_requests", sa.Column("origin_conversation_id", sa.String(length=512)))
    op.create_check_constraint(
        "user_request_origin_required_fields",
        "user_requests",
        "(ingress_key IS NULL AND external_request_id IS NULL "
        "AND origin_actor_id IS NULL AND origin_conversation_id IS NULL) OR "
        "(ingress_key IS NOT NULL AND external_request_id IS NOT NULL)",
    )
    op.create_index(
        "ix_user_requests_origin",
        "user_requests",
        ["ingress_key", "external_request_id"],
    )


def downgrade() -> None:
    """Remove request provenance and restore project-only dispatch keys."""

    op.drop_index("ix_user_requests_origin", table_name="user_requests")
    op.drop_constraint("user_request_origin_required_fields", "user_requests", type_="check")
    op.drop_column("user_requests", "origin_conversation_id")
    op.drop_column("user_requests", "origin_actor_id")
    op.drop_column("user_requests", "external_request_id")
    op.drop_column("user_requests", "ingress_key")

    op.drop_constraint(
        "uq_dispatch_receipts_project_ingress_key",
        "request_dispatch_receipts",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_dispatch_receipts_project_key",
        "request_dispatch_receipts",
        ["project_id", "idempotency_key"],
    )
    op.drop_column("request_dispatch_receipts", "ingress_key")
