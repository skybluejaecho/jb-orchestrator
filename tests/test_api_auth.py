from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.api.security import required_permission
from jb_orchestrator.application import OrchestrationService, SecurityService
from jb_orchestrator.domain import Project
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


async def build_authenticated_app():  # type: ignore[no-untyped-def]
    store = MemoryStore()
    own_project = Project(
        key="alpha", name="Alpha", repository_url="https://example.test/alpha.git"
    )
    other_project = Project(key="beta", name="Beta", repository_url="https://example.test/beta.git")
    store.projects[own_project.id] = own_project
    store.projects[other_project.id] = other_project
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    security = SecurityService(uow)
    issued = await security.issue(
        key="openclaw",
        name="OpenClaw",
        permissions={ApiPermission.PROJECT_READ},
        project_ids={own_project.id},
    )
    app = create_app(
        service=OrchestrationService(uow),
        security_service=security,
        auth_enabled=True,
    )
    return app, security, issued, own_project, other_project


async def test_health_is_public_but_v1_requires_bearer_token() -> None:
    app, _, issued, own_project, _ = await build_authenticated_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health/live")).status_code == 200
        missing = await client.get(f"/v1/projects/{own_project.id}")
        invalid = await client.get(
            f"/v1/projects/{own_project.id}", headers={"Authorization": "Bearer invalid"}
        )
        valid = await client.get(
            f"/v1/projects/{own_project.id}",
            headers={"Authorization": f"Bearer {issued.token}"},
        )

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert valid.status_code == 200


async def test_project_scope_and_permission_are_enforced() -> None:
    app, _, issued, own_project, other_project = await build_authenticated_app()
    headers = {"Authorization": f"Bearer {issued.token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        own = await client.get(f"/v1/projects/{own_project.id}", headers=headers)
        other = await client.get(f"/v1/projects/{other_project.id}", headers=headers)
        global_list = await client.get("/v1/projects", headers=headers)
        dispatch = await client.post(
            f"/v1/projects/{own_project.id}/dispatches",
            headers=headers,
            json={"prompt": "Implement this", "idempotency_key": "test-1"},
        )

    assert own.status_code == 200
    assert other.status_code == 403
    assert global_list.status_code == 403
    assert dispatch.status_code == 403


async def test_revoked_token_is_rejected() -> None:
    app, security, issued, own_project, _ = await build_authenticated_app()
    await security.revoke(issued.account.id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/v1/projects/{own_project.id}",
            headers={"Authorization": f"Bearer {issued.token}"},
        )

    assert response.status_code == 401


def test_workspace_commands_have_a_dedicated_write_permission() -> None:
    execution_id = "00000000-0000-0000-0000-000000000000"
    path = f"/v1/external-executions/{execution_id}/workspace-operations"

    assert required_permission("GET", path) is ApiPermission.PROJECT_READ
    assert required_permission("POST", path) is ApiPermission.WORKSPACE_MANAGE
