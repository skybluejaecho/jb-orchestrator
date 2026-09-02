"""add versioned model profiles

Revision ID: 0007_model_profiles
Revises: 0006_skill_catalog
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_model_profiles"
down_revision: str | None = "0006_skill_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable, versioned model profile entries."""

    op.create_table(
        "model_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("input_cost_per_million", sa.Numeric(18, 6), nullable=False),
        sa.Column("output_cost_per_million", sa.Numeric(18, 6), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("executor_keys", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tier IN ('economy', 'balanced', 'advanced')", name="model_tier"),
        sa.PrimaryKeyConstraint("id", name="pk_model_profiles"),
        sa.UniqueConstraint("key", "version", name="uq_model_profiles_key_version"),
    )
    op.create_index("ix_model_profiles_key", "model_profiles", ["key"])


def downgrade() -> None:
    """Drop the model profile catalog."""

    op.drop_index("ix_model_profiles_key", table_name="model_profiles")
    op.drop_table("model_profiles")
