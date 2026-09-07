"""Installed notification provider discovery and routing."""

from collections.abc import Iterable, Mapping
from importlib.metadata import entry_points
from inspect import iscoroutinefunction
from typing import Any, Protocol

from jb_orchestrator.notifications.models import (
    NotificationProvider,
    NotificationRequest,
    NotificationResult,
)

NOTIFICATION_PROVIDER_ENTRY_POINT_GROUP = "jb_orchestrator.notification_providers"


class NotificationProviderRegistrationError(ValueError):
    """A provider key or installed entry point is invalid."""


class NotificationProviderNotFoundError(LookupError):
    """No installed provider supports the requested key."""


class NotificationProviderEntryPoint(Protocol):
    name: str

    def load(self) -> Any: ...


class NotificationProviderRegistry:
    def __init__(self, providers: Mapping[str, NotificationProvider] | None = None) -> None:
        self._providers: dict[str, NotificationProvider] = {}
        for key, provider in (providers or {}).items():
            self.register(key, provider)

    @property
    def supported_keys(self) -> frozenset[str]:
        return frozenset(self._providers)

    def register(self, key: str, provider: NotificationProvider) -> None:
        normalized = key.strip().lower()
        if not normalized:
            raise NotificationProviderRegistrationError("notification provider key is empty")
        if normalized in self._providers:
            raise NotificationProviderRegistrationError(
                f"notification provider key already registered: {normalized}"
            )
        if not isinstance(provider, NotificationProvider) or not iscoroutinefunction(
            provider.deliver
        ):
            raise NotificationProviderRegistrationError(
                f"provider does not implement async NotificationProvider: {normalized}"
            )
        self._providers[normalized] = provider

    async def deliver(self, provider_key: str, request: NotificationRequest) -> NotificationResult:
        try:
            provider = self._providers[provider_key]
        except KeyError as exc:
            raise NotificationProviderNotFoundError(
                f"notification provider is not registered: {provider_key}"
            ) from exc
        return await provider.deliver(request)

    @classmethod
    def from_entry_points(
        cls, discovered: Iterable[NotificationProviderEntryPoint] | None = None
    ) -> "NotificationProviderRegistry":
        entries = discovered
        if entries is None:
            entries = entry_points(group=NOTIFICATION_PROVIDER_ENTRY_POINT_GROUP)
        registry = cls()
        for entry in entries:
            factory = entry.load()
            if not callable(factory):
                raise NotificationProviderRegistrationError(
                    f"notification provider entry point must load a factory: {entry.name}"
                )
            try:
                provider = factory()
            except Exception as exc:
                raise NotificationProviderRegistrationError(
                    f"notification provider factory failed: {entry.name}"
                ) from exc
            registry.register(entry.name, provider)
        return registry
