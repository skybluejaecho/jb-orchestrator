"""add external execution workspace metadata

Revision ID: 0017_execution_workspaces
Revises: 0016_service_accounts
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_execution_workspaces"
down_revision: str | None = "0016_service_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_executions",
        sa.Column("workspace_path", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "external_executions",
        sa.Column("workspace_branch", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "external_executions",
        sa.Column("workspace_base_ref", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_executions", "workspace_base_ref")
    op.drop_column("external_executions", "workspace_branch")
    op.drop_column("external_executions", "workspace_path")
