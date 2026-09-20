"""track SCM publication attempts

Revision ID: 0021_scm_publication_attempts
Revises: 0020_scm_publications
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_scm_publication_attempts"
down_revision: str | None = "0020_scm_publications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scm_publications",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("scm_publications", "attempt_count")
