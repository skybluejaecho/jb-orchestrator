from uuid import uuid4

import pytest

from jb_orchestrator.application import SecurityService
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import Project
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_issue_authenticate_and_revoke_service_account() -> None:
    store = MemoryStore()
    project = Project(key="alpha", name="Alpha", repository_url="https://example.test/a.git")
    store.projects[project.id] = project
    service = SecurityService(lambda: MemoryUnitOfWork(store))

    issued = await service.issue(
        key="openclaw",
        name="OpenClaw",
        permissions={ApiPermission.PROJECT_READ, ApiPermission.REQUEST_DISPATCH},
        project_ids={project.id},
    )

    assert issued.token.startswith(f"jbsa_{issued.account.id.hex}.")
    assert issued.token not in issued.account.token_digest
    principal = await service.authenticate(issued.token)
    assert principal is not None
    assert principal.allows(ApiPermission.REQUEST_DISPATCH, project.id)
    assert await service.authenticate(f"{issued.token}wrong") is None

    await service.revoke(issued.account.id)
    assert await service.authenticate(issued.token) is None


async def test_issue_rejects_duplicate_key_and_missing_project() -> None:
    store = MemoryStore()
    service = SecurityService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(ResourceNotFound, match="project not found"):
        await service.issue(
            key="missing-project",
            name="Missing",
            permissions={ApiPermission.PROJECT_READ},
            project_ids={uuid4()},
        )

    first = await service.issue(
        key="global-admin",
        name="Global Admin",
        permissions={ApiPermission.PROJECT_ADMIN},
        all_projects=True,
    )
    assert first.account.all_projects
    with pytest.raises(ResourceConflict, match="already exists"):
        await service.issue(
            key="global-admin",
            name="Duplicate",
            permissions={ApiPermission.PROJECT_ADMIN},
            all_projects=True,
        )
