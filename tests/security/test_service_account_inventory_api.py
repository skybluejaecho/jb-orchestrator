from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, SecurityService
from jb_orchestrator.domain import Project
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_global_admin_lists_and_inspects_service_account_inventory() -> None:
    store = MemoryStore()
    project = Project(key="alpha", name="Alpha", repository_url="https://example.test/a.git")
    store.projects[project.id] = project
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    security = SecurityService(uow)
    admin = await security.issue(
        key="global-admin",
        name="Global Admin",
        permissions={ApiPermission.PROJECT_ADMIN},
        all_projects=True,
    )
    jarvis = await security.issue(
        key="jarvis-local",
        name="Jarvis",
        permissions={ApiPermission.PROJECT_READ},
        project_ids={project.id},
    )
    replacement = await security.issue_credential(jarvis.account.id)
    await security.revoke_credential(jarvis.account.id, jarvis.credential.id)
    scoped_admin = await security.issue(
        key="scoped-admin",
        name="Scoped Admin",
        permissions={ApiPermission.PROJECT_ADMIN},
        project_ids={project.id},
    )
    app = create_app(
        service=OrchestrationService(uow),
        security_service=security,
        auth_enabled=True,
    )
    admin_headers = {"Authorization": f"Bearer {admin.token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get(
            "/v1/service-accounts",
            params={"key_prefix": "jarvis", "enabled": "true", "limit": 10},
            headers=admin_headers,
        )
        detail = await client.get(
            f"/v1/service-accounts/{jarvis.account.id}",
            headers=admin_headers,
        )
        client_forbidden = await client.get(
            "/v1/service-accounts",
            headers={"Authorization": f"Bearer {replacement.token}"},
        )
        scoped_forbidden = await client.get(
            "/v1/service-accounts",
            headers={"Authorization": f"Bearer {scoped_admin.token}"},
        )
        invalid_filter = await client.get(
            "/v1/service-accounts",
            params={"key_prefix": "%"},
            headers=admin_headers,
        )

    assert listed.status_code == 200
    assert listed.json() == [detail.json()]
    payload = detail.json()
    assert payload["id"] == str(jarvis.account.id)
    assert payload["key"] == "jarvis-local"
    assert payload["permissions"] == ["project.read"]
    assert payload["project_ids"] == [str(project.id)]
    summary = payload["credential_summary"]
    assert {key: summary[key] for key in ("total", "active", "usable", "expired", "revoked")} == {
        "total": 2,
        "active": 1,
        "usable": 1,
        "expired": 0,
        "revoked": 1,
    }
    assert summary["latest_created_at"] is not None
    assert summary["last_used_at"] is None
    assert "token" not in detail.text
    assert "token_digest" not in detail.text
    assert client_forbidden.status_code == 403
    assert scoped_forbidden.status_code == 403
    assert invalid_filter.status_code == 422


async def test_service_account_inventory_uses_key_cursor_and_enabled_filter() -> None:
    store = MemoryStore()
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    security = SecurityService(uow)
    admin = await security.issue(
        key="admin-root",
        name="Admin",
        permissions={ApiPermission.PROJECT_ADMIN},
        all_projects=True,
    )
    middle = await security.issue(
        key="client-middle",
        name="Middle",
        permissions={ApiPermission.PROJECT_READ},
        all_projects=True,
    )
    disabled = await security.issue(
        key="client-zeta",
        name="Zeta",
        permissions={ApiPermission.PROJECT_READ},
        all_projects=True,
    )
    await security.revoke(disabled.account.id)
    app = create_app(
        service=OrchestrationService(uow),
        security_service=security,
        auth_enabled=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/v1/service-accounts",
            params={"after_key": middle.account.key, "enabled": "false", "limit": 1},
            headers={"Authorization": f"Bearer {admin.token}"},
        )

    assert response.status_code == 200
    assert [account["key"] for account in response.json()] == ["client-zeta"]
    assert response.json()[0]["credential_summary"]["active"] == 1
    assert response.json()[0]["credential_summary"]["usable"] == 0
