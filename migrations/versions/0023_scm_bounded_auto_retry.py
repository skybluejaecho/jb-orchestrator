"""schedule bounded automatic SCM retries

Revision ID: 0023_scm_bounded_auto_retry
Revises: 0022_scm_failure_classification
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_scm_bounded_auto_retry"
down_revision: str | None = "0022_scm_failure_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scm_publications",
        sa.Column("automatic_retry_limit", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "scm_publications",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_scm_publications_next_attempt_at",
        "scm_publications",
        ["next_attempt_at"],
    )
    op.create_check_constraint(
        "automatic_retry_limit",
        "scm_publications",
        "automatic_retry_limit BETWEEN 0 AND 10",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE scm_publications "
        "DROP CONSTRAINT IF EXISTS ck_scm_publications_automatic_retry_limit"
    )
    op.drop_index("ix_scm_publications_next_attempt_at", table_name="scm_publications")
    op.drop_column("scm_publications", "next_attempt_at")
    op.drop_column("scm_publications", "automatic_retry_limit")
