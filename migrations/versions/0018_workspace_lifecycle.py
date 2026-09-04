"""add external workspace lifecycle metadata

Revision ID: 0018_workspace_lifecycle
Revises: 0017_execution_workspaces
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_workspace_lifecycle"
down_revision: str | None = "0017_execution_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "external_executions",
        sa.Column("workspace_repository_path", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "external_executions",
        sa.Column("workspace_released_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_executions", "workspace_released_at")
    op.drop_column("external_executions", "workspace_repository_path")
