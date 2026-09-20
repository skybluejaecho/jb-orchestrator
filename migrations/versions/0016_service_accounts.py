"""add scoped service accounts

Revision ID: 0016_service_accounts
Revises: 0015_request_origins
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_service_accounts"
down_revision: str | None = "0015_request_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_digest", sa.String(length=71), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("project_ids", sa.JSON(), nullable=False),
        sa.Column("all_projects", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_service_accounts"),
        sa.UniqueConstraint("key", name="uq_service_accounts_key"),
    )


def downgrade() -> None:
    op.drop_table("service_accounts")
