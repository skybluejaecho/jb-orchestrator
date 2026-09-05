from dataclasses import dataclass
from typing import Any

import pytest

from jb_orchestrator.scm import (
    ScmPublicationRequest,
    ScmPublicationResult,
    ScmPublisherNotFoundError,
    ScmPublisherRegistrationError,
    ScmPublisherRegistry,
)


class StubPublisher:
    def __init__(self) -> None:
        self.requests: list[ScmPublicationRequest] = []

    async def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult:
        self.requests.append(request)
        return ScmPublicationResult(
            provider="stub",
            repository=request.repository,
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            review_url="https://scm.example/reviews/49",
            review_id="49",
        )


class SyncPublisher:
    def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult:
        raise NotImplementedError


@dataclass
class StubEntryPoint:
    name: str
    value: Any

    def load(self) -> Any:
        return self.value


def publication_request() -> ScmPublicationRequest:
    return ScmPublicationRequest(
        repository="owner/repository",
        source_branch="feature/work",
        target_branch="develop",
        title="Review work",
        body="Details",
        idempotency_key="request-1",
    )


async def test_registry_routes_to_explicit_provider() -> None:
    publisher = StubPublisher()
    registry = ScmPublisherRegistry({"github": publisher})

    result = await registry.publish_review("github", publication_request())

    assert result.review_id == "49"
    assert publisher.requests == [publication_request()]
    assert registry.supported_keys == frozenset({"github"})


async def test_registry_rejects_unknown_provider() -> None:
    registry = ScmPublisherRegistry()

    with pytest.raises(ScmPublisherNotFoundError, match="gitlab"):
        await registry.publish_review("gitlab", publication_request())


def test_registry_rejects_duplicate_or_synchronous_adapter() -> None:
    registry = ScmPublisherRegistry({"github": StubPublisher()})
    with pytest.raises(ScmPublisherRegistrationError, match="already registered"):
        registry.register("github", StubPublisher())
    with pytest.raises(ScmPublisherRegistrationError, match="must be async"):
        registry.register("sync", SyncPublisher())  # type: ignore[arg-type]


def test_registry_loads_installed_factories() -> None:
    publisher = StubPublisher()
    registry = ScmPublisherRegistry.from_entry_points(
        [StubEntryPoint(name="gitlab", value=lambda: publisher)]
    )

    assert registry.supported_keys == frozenset({"gitlab"})


@pytest.mark.parametrize("loaded", [object(), lambda: object()])
def test_registry_rejects_invalid_entry_points(loaded: object) -> None:
    with pytest.raises(ScmPublisherRegistrationError):
        ScmPublisherRegistry.from_entry_points([StubEntryPoint(name="invalid", value=loaded)])
