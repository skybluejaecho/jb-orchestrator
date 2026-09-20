"""Installed SCM publication adapter discovery and routing."""

from collections.abc import Iterable, Mapping
from importlib.metadata import entry_points
from inspect import iscoroutinefunction
from typing import Any, Protocol

from jb_orchestrator.scm.models import (
    ScmPublicationRequest,
    ScmPublicationResult,
    ScmPublisher,
)

SCM_PUBLISHER_ENTRY_POINT_GROUP = "jb_orchestrator.scm_publishers"


class ScmPublisherRegistrationError(ValueError):
    """An SCM provider key or installed entry point is invalid."""


class ScmPublisherNotFoundError(LookupError):
    """No registered adapter supports the requested SCM provider."""


class ScmPublisherEntryPoint(Protocol):
    name: str

    def load(self) -> Any: ...


class ScmPublisherRegistry:
    """Route publication requests to explicitly registered SCM adapters."""

    def __init__(self, publishers: Mapping[str, ScmPublisher] | None = None) -> None:
        self._publishers: dict[str, ScmPublisher] = {}
        for key, publisher in (publishers or {}).items():
            self.register(key, publisher)

    @property
    def supported_keys(self) -> frozenset[str]:
        return frozenset(self._publishers)

    def register(self, key: str, publisher: ScmPublisher) -> None:
        normalized = key.strip()
        if not normalized:
            raise ScmPublisherRegistrationError("SCM publisher key must not be empty")
        if normalized in self._publishers:
            raise ScmPublisherRegistrationError(
                f"SCM publisher key already registered: {normalized}"
            )
        if not isinstance(publisher, ScmPublisher):
            raise ScmPublisherRegistrationError(
                f"publisher does not implement ScmPublisher: {normalized}"
            )
        if not iscoroutinefunction(publisher.publish_review):
            raise ScmPublisherRegistrationError(
                f"publisher publish_review method must be async: {normalized}"
            )
        self._publishers[normalized] = publisher

    async def publish_review(
        self, provider_key: str, request: ScmPublicationRequest
    ) -> ScmPublicationResult:
        try:
            publisher = self._publishers[provider_key]
        except KeyError as exc:
            raise ScmPublisherNotFoundError(
                f"SCM publisher is not registered: {provider_key}"
            ) from exc
        return await publisher.publish_review(request)

    @classmethod
    def from_entry_points(
        cls, discovered: Iterable[ScmPublisherEntryPoint] | None = None
    ) -> "ScmPublisherRegistry":
        """Load no-argument publisher factories installed under the public plugin group."""

        entries = discovered
        if entries is None:
            entries = entry_points(group=SCM_PUBLISHER_ENTRY_POINT_GROUP)
        registry = cls()
        for entry in entries:
            factory = entry.load()
            if not callable(factory):
                raise ScmPublisherRegistrationError(
                    f"SCM publisher entry point must load a callable factory: {entry.name}"
                )
            try:
                publisher = factory()
            except Exception as exc:
                raise ScmPublisherRegistrationError(
                    f"SCM publisher factory failed: {entry.name}"
                ) from exc
            if not isinstance(publisher, ScmPublisher):
                raise ScmPublisherRegistrationError(
                    f"SCM publisher factory returned an invalid adapter: {entry.name}"
                )
            registry.register(entry.name, publisher)
        return registry
