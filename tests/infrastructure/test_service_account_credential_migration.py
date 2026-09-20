import asyncio
import importlib
import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import SecurityService
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork


def database_urls(path: Path) -> tuple[str, str]:
    sync_url = f"sqlite:///{path.resolve().as_posix()}"
    return sync_url, sync_url.replace("sqlite:///", "sqlite+aiosqlite:///")


def run_migration(connection: sa.Connection, direction: str) -> None:
    migration = importlib.import_module("migrations.versions.0032_service_account_credentials")
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        getattr(migration, direction)()


def test_migration_preserves_existing_bearer_token(tmp_path: Path) -> None:
    account_id = uuid4()
    project_id = uuid4()
    token = f"jbsa_{account_id.hex}.legacy-secret"
    digest = f"sha256:{sha256(token.encode()).hexdigest()}"
    sync_url, async_url = database_urls(tmp_path / "credentials.db")
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE service_accounts ("
                "id CHAR(32) PRIMARY KEY, key VARCHAR(64) NOT NULL UNIQUE, "
                "name VARCHAR(255) NOT NULL, token_digest VARCHAR(71) NOT NULL, "
                "permissions JSON NOT NULL, project_ids JSON NOT NULL, "
                "all_projects BOOLEAN NOT NULL, enabled BOOLEAN NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO service_accounts "
                "(id, key, name, token_digest, permissions, project_ids, "
                "all_projects, enabled, created_at) "
                "VALUES (:id, :key, :name, :digest, :permissions, :project_ids, 0, 1, :created)"
            ),
            {
                "id": account_id.hex,
                "key": "legacy-jarvis",
                "name": "Legacy Jarvis",
                "digest": digest,
                "permissions": json.dumps(["project.read"]),
                "project_ids": json.dumps([str(project_id)]),
                "created": "2026-09-08 00:00:00.000000",
            },
        )
        run_migration(connection, "upgrade")

    with engine.connect() as connection:
        migrated = connection.execute(
            text("SELECT id, account_id, token_digest FROM service_account_credentials")
        ).one()
    assert UUID(migrated.id) == account_id
    assert UUID(migrated.account_id) == account_id
    assert migrated.token_digest == digest

    async def authenticate() -> None:
        async_engine = create_async_engine(async_url)
        session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        principal = await SecurityService(
            lambda: SqlAlchemyUnitOfWork(session_factory)
        ).authenticate(token)
        assert principal is not None
        assert principal.account_id == account_id
        assert principal.credential_id == account_id
        await async_engine.dispose()

    asyncio.run(authenticate())

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO service_account_credentials "
                "(id, account_id, token_digest, created_at) "
                "VALUES (:id, :account_id, :digest, :created)"
            ),
            {
                "id": uuid4().hex,
                "account_id": account_id.hex,
                "digest": f"sha256:{'f' * 64}",
                "created": "2026-09-09 00:00:00.000000",
            },
        )
        with pytest.raises(RuntimeError, match="cannot downgrade credential lifecycle"):
            run_migration(connection, "downgrade")
        connection.execute(
            text("DELETE FROM service_account_credentials WHERE id <> :id"),
            {"id": account_id.hex},
        )
        run_migration(connection, "downgrade")
        restored_digest = connection.execute(
            text("SELECT token_digest FROM service_accounts WHERE id = :id"),
            {"id": account_id.hex},
        ).scalar_one()
    assert restored_digest == digest
    engine.dispose()
