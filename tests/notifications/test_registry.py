from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from jb_orchestrator.notifications import (
    NotificationEventType,
    NotificationProviderNotFoundError,
    NotificationProviderRegistrationError,
    NotificationProviderRegistry,
    NotificationRequest,
    NotificationResult,
)


class Provider:
    def __init__(self) -> None:
        self.requests: list[NotificationRequest] = []

    async def deliver(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        return NotificationResult(output={"idempotency_key": request.idempotency_key})


class SyncProvider:
    def deliver(self, request: NotificationRequest) -> NotificationResult:
        raise NotImplementedError


@dataclass
class EntryPoint:
    name: str
    value: Any

    def load(self) -> Any:
        return self.value


def request() -> NotificationRequest:
    return NotificationRequest(
        delivery_id=uuid4(),
        project_id=uuid4(),
        event_type=NotificationEventType.WORKER_READINESS_ALERTED,
        destination_ref="ops",
        payload={"message": "alert"},
        idempotency_key="notification-1",
    )


async def test_registry_routes_to_provider() -> None:
    provider = Provider()
    registry = NotificationProviderRegistry({"fixture": provider})
    result = await registry.deliver("fixture", request())
    assert result.output == {"idempotency_key": "notification-1"}
    assert len(provider.requests) == 1


async def test_registry_rejects_unknown_provider() -> None:
    with pytest.raises(NotificationProviderNotFoundError, match="missing"):
        await NotificationProviderRegistry().deliver("missing", request())


def test_registry_discovers_factory() -> None:
    registry = NotificationProviderRegistry.from_entry_points(
        [EntryPoint(name="fixture", value=Provider)]
    )
    assert registry.supported_keys == frozenset({"fixture"})


def test_registry_rejects_duplicate_key() -> None:
    registry = NotificationProviderRegistry({"fixture": Provider()})
    with pytest.raises(NotificationProviderRegistrationError):
        registry.register("fixture", Provider())


def test_registry_rejects_synchronous_provider() -> None:
    with pytest.raises(NotificationProviderRegistrationError, match="async"):
        NotificationProviderRegistry().register("sync", SyncProvider())  # type: ignore[arg-type]


def test_registry_hides_factory_failure_details() -> None:
    def failing_factory() -> object:
        raise RuntimeError("secret configuration detail")

    with pytest.raises(NotificationProviderRegistrationError, match=r"failed: fixture$") as error:
        NotificationProviderRegistry.from_entry_points(
            [EntryPoint(name="fixture", value=failing_factory)]
        )
    assert "secret configuration detail" not in str(error.value)
