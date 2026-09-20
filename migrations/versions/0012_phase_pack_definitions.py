"""add versioned phase pack definitions

Revision ID: 0012_phase_packs
Revises: 0011_task_artifacts
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_phase_packs"
down_revision: str | None = "0011_task_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the immutable phase-pack catalog."""

    op.create_table(
        "phase_pack_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("output_contract", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_phase_pack_definitions"),
        sa.UniqueConstraint("key", "version", name="uq_phase_pack_definitions_key_version"),
    )
    op.create_index("ix_phase_pack_definitions_key", "phase_pack_definitions", ["key"])


def downgrade() -> None:
    """Drop the phase-pack catalog."""

    op.drop_index("ix_phase_pack_definitions_key", table_name="phase_pack_definitions")
    op.drop_table("phase_pack_definitions")
