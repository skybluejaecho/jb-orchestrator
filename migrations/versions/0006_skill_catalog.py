"""add versioned skill catalog

Revision ID: 0006_skill_catalog
Revises: 0005_executor_routing
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_skill_catalog"
down_revision: str | None = "0005_executor_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable, versioned skill catalog entries."""

    op.create_table(
        "skill_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=False),
        sa.Column("content_digest", sa.String(length=71), nullable=False),
        sa.Column("source_revision", sa.String(length=255), nullable=True),
        sa.Column("entrypoint", sa.String(length=1024), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_kind IN ('local', 'git', 'archive')", name="skill_source_kind"),
        sa.PrimaryKeyConstraint("id", name="pk_skill_definitions"),
        sa.UniqueConstraint("key", "version", name="uq_skill_definitions_key_version"),
    )
    op.create_index("ix_skill_definitions_key", "skill_definitions", ["key"])


def downgrade() -> None:
    """Drop the skill catalog."""

    op.drop_index("ix_skill_definitions_key", table_name="skill_definitions")
    op.drop_table("skill_definitions")
