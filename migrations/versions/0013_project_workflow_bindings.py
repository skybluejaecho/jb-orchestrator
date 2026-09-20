"""add project workflow bindings

Revision ID: 0013_workflow_bindings
Revises: 0012_phase_packs
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_workflow_bindings"
down_revision: str | None = "0012_phase_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one exact workflow binding per project."""

    op.create_table(
        "project_workflow_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("definition_key", sa.String(length=128), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["workflow_definitions.id"],
            name="fk_binding_definition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_binding_project", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_workflow_bindings"),
        sa.UniqueConstraint("project_id", name="uq_project_workflow_bindings_project_id"),
    )


def downgrade() -> None:
    """Drop project workflow bindings."""

    op.drop_table("project_workflow_bindings")
