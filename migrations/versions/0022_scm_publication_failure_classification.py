"""classify SCM publication failures

Revision ID: 0022_scm_failure_classification
Revises: 0021_scm_publication_attempts
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_scm_failure_classification"
down_revision: str | None = "0021_scm_publication_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


failure_code = sa.Enum(
    "workspace_state",
    "provider_rejected",
    "provider_unavailable",
    "timeout",
    "result_mismatch",
    "unexpected",
    name="scm_publication_failure_code",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.add_column("scm_publications", sa.Column("failure_code", failure_code, nullable=True))
    op.add_column("scm_publications", sa.Column("failure_retryable", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("scm_publications", "failure_retryable")
    op.drop_column("scm_publications", "failure_code")
