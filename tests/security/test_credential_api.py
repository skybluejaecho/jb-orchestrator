from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import OrchestrationService, SecurityService
from jb_orchestrator.domain import Project
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_global_admin_rotates_service_account_credentials() -> None:
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
    client_account = await security.issue(
        key="jarvis",
        name="Jarvis",
        permissions={ApiPermission.PROJECT_READ},
        project_ids={project.id},
    )
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
    base_path = f"/v1/service-accounts/{client_account.account.id}/credentials"
    admin_headers = {"Authorization": f"Bearer {admin.token}"}
    client_headers = {"Authorization": f"Bearer {client_account.token}"}
    scoped_admin_headers = {"Authorization": f"Bearer {scoped_admin.token}"}
    expires_at = datetime.now(UTC) + timedelta(days=7)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forbidden = await client.get(base_path, headers=client_headers)
        scoped_forbidden = await client.get(base_path, headers=scoped_admin_headers)
        issued = await client.post(
            base_path,
            headers=admin_headers,
            json={"expires_at": expires_at.isoformat()},
        )
        listed = await client.get(base_path, headers=admin_headers)
        credential_id = issued.json()["id"]
        issued_principal = await security.authenticate(issued.json()["token"])
        revoked = await client.delete(
            f"{base_path}/{credential_id}",
            headers=admin_headers,
        )
        audited = await client.get(
            f"/v1/service-accounts/{client_account.account.id}/credential-events",
            headers=admin_headers,
        )

    assert forbidden.status_code == 403
    assert scoped_forbidden.status_code == 403
    assert issued.status_code == 201
    assert issued.json()["token"].startswith(f"jbsa_{credential_id.replace('-', '')}.")
    assert issued.json()["warning"]
    assert len(listed.json()) == 2
    assert all("token" not in credential for credential in listed.json())
    assert all("token_digest" not in credential for credential in listed.json())
    assert issued_principal is not None
    assert issued_principal.account_id == client_account.account.id
    assert revoked.status_code == 200
    assert revoked.json() == {
        "account_id": str(client_account.account.id),
        "credential_id": credential_id,
        "revoked": True,
    }
    assert audited.status_code == 200
    assert [event["event_type"] for event in audited.json()] == [
        "service_account.credential_revoked",
        "service_account.credential_issued",
        "service_account.credential_issued",
    ]
    assert audited.json()[0]["credential_id"] == credential_id
    assert audited.json()[0]["actor_account_id"] == str(admin.account.id)
    assert audited.json()[0]["actor_credential_id"] == str(admin.credential.id)
    assert "token" not in audited.text
    assert "token_digest" not in audited.text
    assert await security.authenticate(issued.json()["token"]) is None


async def test_credential_management_is_unavailable_without_api_authentication() -> None:
    store = MemoryStore()
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    security = SecurityService(uow)
    account = await security.issue(
        key="global-admin",
        name="Global Admin",
        permissions={ApiPermission.PROJECT_ADMIN},
        all_projects=True,
    )
    app = create_app(
        service=OrchestrationService(uow),
        security_service=security,
        auth_enabled=False,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/service-accounts/{account.account.id}/credentials")

    assert response.status_code == 503
