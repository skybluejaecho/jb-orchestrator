"""add monotonic event sequence

Revision ID: 0010_event_sequence
Revises: 0009_external_executions
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_event_sequence"
down_revision: str | None = "0009_external_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a database-issued total order for durable event replay."""

    op.add_column(
        "events",
        sa.Column(
            "sequence",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
    )
    op.drop_constraint("pk_events", "events", type_="primary")
    op.create_primary_key("pk_events", "events", ["sequence"])
    op.create_unique_constraint("uq_events_id", "events", ["id"])
    op.create_index(
        "ix_events_aggregate_type_sequence",
        "events",
        ["aggregate_type", "sequence"],
    )


def downgrade() -> None:
    """Restore UUID-only event identity."""

    op.drop_index("ix_events_aggregate_type_sequence", table_name="events")
    op.drop_constraint("pk_events", "events", type_="primary")
    op.drop_constraint("uq_events_id", "events", type_="unique")
    op.create_primary_key("pk_events", "events", ["id"])
    op.drop_column("events", "sequence")
