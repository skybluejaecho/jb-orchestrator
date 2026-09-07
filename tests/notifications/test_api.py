from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import NotificationService, SecurityService
from jb_orchestrator.domain import Project
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationEventType,
    NotificationFailureCode,
)
from jb_orchestrator.security import ApiPermission
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_notification_subscription_api_creates_lists_and_configures() -> None:
    store = MemoryStore()
    project = Project(
        key="notification-api",
        name="Notification API",
        repository_url="https://github.com/example/notification-api.git",
    )
    store.projects[project.id] = project
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    app = create_app(notification_service=service, auth_enabled=False)
    create_payload = {
        "provider_key": "webhook",
        "destination_ref": "operations-primary",
        "event_types": ["worker.readiness_alerted", "worker.readiness_critical"],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            f"/v1/projects/{project.id}/notification-subscriptions",
            json=create_payload,
        )
        replayed = await client.post(
            f"/v1/projects/{project.id}/notification-subscriptions",
            json=create_payload,
        )
        listed = await client.get(f"/v1/projects/{project.id}/notification-subscriptions")
        configured = await client.patch(
            f"/v1/projects/{project.id}/notification-subscriptions/{created.json()['id']}",
            json={
                "event_types": ["worker.readiness_resolved"],
                "enabled": False,
            },
        )
        deliveries = await client.get(f"/v1/projects/{project.id}/notification-deliveries")

    assert created.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json()["id"] == created.json()["id"]
    assert [value["id"] for value in listed.json()] == [created.json()["id"]]
    assert configured.status_code == 200
    assert configured.json()["event_types"] == ["worker.readiness_resolved"]
    assert not configured.json()["enabled"]
    assert deliveries.status_code == 200
    assert deliveries.json() == []


async def test_notification_subscription_write_requires_dedicated_permission() -> None:
    store = MemoryStore()
    project = Project(
        key="notification-auth",
        name="Notification Auth",
        repository_url="https://github.com/example/notification-auth.git",
    )
    store.projects[project.id] = project
    uow = lambda: MemoryUnitOfWork(store)  # noqa: E731
    security = SecurityService(uow)
    reader = await security.issue(
        key="notification-reader",
        name="Notification Reader",
        permissions=(ApiPermission.PROJECT_READ,),
        project_ids=(project.id,),
    )
    manager = await security.issue(
        key="notification-manager",
        name="Notification Manager",
        permissions=(ApiPermission.NOTIFICATION_MANAGE,),
        project_ids=(project.id,),
    )
    app = create_app(
        notification_service=NotificationService(uow),
        security_service=security,
        auth_enabled=True,
    )
    path = f"/v1/projects/{project.id}/notification-subscriptions"
    payload = {
        "provider_key": "webhook",
        "destination_ref": "operations-primary",
        "event_types": ["worker.readiness_critical"],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forbidden = await client.post(
            path,
            headers={"Authorization": f"Bearer {reader.token}"},
            json=payload,
        )
        created = await client.post(
            path,
            headers={"Authorization": f"Bearer {manager.token}"},
            json=payload,
        )
        readable = await client.get(
            path,
            headers={"Authorization": f"Bearer {reader.token}"},
        )

    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert readable.status_code == 200


async def test_notification_delivery_attempts_and_manual_retry_api() -> None:
    store = MemoryStore()
    project = Project(
        key="notification-retry-api",
        name="Notification Retry API",
        repository_url="https://example.com/notification-retry-api.git",
    )
    store.projects[project.id] = project
    delivery = NotificationDelivery(
        subscription_id=project.id,
        project_id=project.id,
        event_id=project.id,
        alert_id=project.id,
        event_type=NotificationEventType.WORKER_READINESS_ALERTED,
        provider_key="webhook",
        destination_ref="ops",
        payload={"message": "alert"},
        idempotency_key="notification:retry-api",
    )
    store.notification_deliveries[delivery.id] = delivery
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    claimed = await service.claim_next(worker_id="worker-1", provider_key="webhook")
    assert claimed is not None and claimed.lease_token is not None
    await service.fail(
        claimed.id,
        claimed.lease_token,
        "provider unavailable",
        code=NotificationFailureCode.PROVIDER_UNAVAILABLE,
    )
    app = create_app(notification_service=service, auth_enabled=False)
    base = f"/v1/projects/{project.id}/notification-deliveries/{delivery.id}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        attempts = await client.get(f"{base}/attempts")
        retried = await client.post(f"{base}/retry")
        replayed = await client.post(f"{base}/retry")

    assert attempts.status_code == 200
    assert attempts.json()[0]["trigger"] == "initial"
    assert attempts.json()[0]["status"] == "failed"
    assert "lease_token" not in attempts.json()[0]
    assert retried.status_code == 202
    assert retried.json()["status"] == "pending"
    assert replayed.status_code == 200
