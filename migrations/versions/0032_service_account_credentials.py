"""separate service account credentials

Revision ID: 0032_service_account_credentials
Revises: 0031_notification_auto_retry
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_service_account_credentials"
down_revision: str | None = "0031_notification_auto_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_account_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name="ck_service_account_credentials_credential_expiration_after_creation",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_service_account_credentials_credential_revocation_after_creation",
        ),
        sa.CheckConstraint(
            "last_used_at IS NULL OR last_used_at >= created_at",
            name="ck_service_account_credentials_credential_usage_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["service_accounts.id"],
            name="fk_service_account_credentials_account_id_service_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_service_account_credentials"),
    )
    op.create_index(
        "ix_service_account_credentials_account_id",
        "service_account_credentials",
        ["account_id"],
    )
    op.create_index(
        "ix_service_account_credentials_expires_at",
        "service_account_credentials",
        ["expires_at"],
    )
    op.execute(
        sa.text(
            "INSERT INTO service_account_credentials "
            "(id, account_id, token_digest, created_at) "
            "SELECT id, id, token_digest, created_at FROM service_accounts"
        )
    )
    with op.batch_alter_table("service_accounts") as batch_op:
        batch_op.drop_column("token_digest")


def downgrade() -> None:
    unsafe_count = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM service_accounts AS account "
            "WHERE (SELECT COUNT(*) FROM service_account_credentials AS credential "
            "WHERE credential.account_id = account.id) <> 1 "
            "OR EXISTS (SELECT 1 FROM service_account_credentials AS credential "
            "WHERE credential.account_id = account.id "
            "AND (credential.expires_at IS NOT NULL OR credential.revoked_at IS NOT NULL))"
        )
    )
    if unsafe_count:
        raise RuntimeError(
            "cannot downgrade credential lifecycle with multiple, expiring, or revoked credentials"
        )
    with op.batch_alter_table("service_accounts") as batch_op:
        batch_op.add_column(sa.Column("token_digest", sa.String(length=71), nullable=True))
    op.execute(
        sa.text(
            "UPDATE service_accounts SET token_digest = ("
            "SELECT token_digest FROM service_account_credentials "
            "WHERE account_id = service_accounts.id "
            "ORDER BY created_at, id LIMIT 1)"
        )
    )
    with op.batch_alter_table("service_accounts") as batch_op:
        batch_op.alter_column("token_digest", existing_type=sa.String(length=71), nullable=False)
    op.drop_index(
        "ix_service_account_credentials_expires_at",
        table_name="service_account_credentials",
    )
    op.drop_index(
        "ix_service_account_credentials_account_id",
        table_name="service_account_credentials",
    )
    op.drop_table("service_account_credentials")
