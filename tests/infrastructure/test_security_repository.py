from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import OrchestrationService, RegisterProject, SecurityService
from jb_orchestrator.infrastructure.database import Base, SqlAlchemyUnitOfWork
from jb_orchestrator.security import ApiPermission


async def test_service_account_round_trip_and_revocation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    orchestration = OrchestrationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    project = await orchestration.register_project(
        RegisterProject(key="alpha", name="Alpha", repository_url="https://example.test/a.git")
    )
    security = SecurityService(lambda: SqlAlchemyUnitOfWork(session_factory))

    issued = await security.issue(
        key="openclaw",
        name="OpenClaw",
        permissions={ApiPermission.PROJECT_READ},
        project_ids={project.id},
    )
    replacement = await security.issue_credential(issued.account.id)

    assert await security.authenticate(issued.token) is not None
    assert await security.authenticate(replacement.token) is not None
    async with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        credentials = await unit_of_work.service_account_credentials.list_for_account(
            issued.account.id
        )
    assert {credential.id for credential in credentials} == {
        issued.credential.id,
        replacement.credential.id,
    }
    assert all(credential.last_used_at is not None for credential in credentials)
    await security.revoke_credential(issued.credential.id)
    assert await security.authenticate(issued.token) is None
    assert await security.authenticate(replacement.token) is not None
    await security.revoke(issued.account.id)
    assert await security.authenticate(replacement.token) is None
    await engine.dispose()
