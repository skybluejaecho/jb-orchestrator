"""Installed executor adapter discovery and routing."""

from collections.abc import Iterable, Mapping
from importlib.metadata import entry_points
from inspect import iscoroutinefunction
from typing import Any, Protocol

from jb_orchestrator.worker.models import (
    CancellableTaskExecutor,
    TaskClaim,
    TaskExecutor,
    TaskResult,
)

EXECUTOR_ENTRY_POINT_GROUP = "jb_orchestrator.executors"


class ExecutorRegistrationError(ValueError):
    """An executor key or installed entry point is invalid."""


class ExecutorNotFoundError(LookupError):
    """No registered adapter supports a claimed executor key."""


class ExecutorEntryPoint(Protocol):
    name: str

    def load(self) -> Any: ...


class ExecutorRegistry:
    """Route claims to explicitly registered executor adapters."""

    def __init__(self, executors: Mapping[str, TaskExecutor] | None = None) -> None:
        self._executors: dict[str, TaskExecutor] = {}
        for key, executor in (executors or {}).items():
            self.register(key, executor)

    @property
    def supported_keys(self) -> frozenset[str]:
        return frozenset(self._executors)

    def register(self, key: str, executor: TaskExecutor) -> None:
        normalized = key.strip()
        if not normalized:
            raise ExecutorRegistrationError("executor key must not be empty")
        if normalized in self._executors:
            raise ExecutorRegistrationError(f"executor key already registered: {normalized}")
        if not isinstance(executor, TaskExecutor):
            raise ExecutorRegistrationError(
                f"executor does not implement TaskExecutor: {normalized}"
            )
        if not iscoroutinefunction(executor.execute):
            raise ExecutorRegistrationError(f"executor execute method must be async: {normalized}")
        if isinstance(executor, CancellableTaskExecutor) and not iscoroutinefunction(
            executor.cancel
        ):
            raise ExecutorRegistrationError(f"executor cancel method must be async: {normalized}")
        self._executors[normalized] = executor

    async def execute(self, claim: TaskClaim) -> TaskResult:
        executor = self._get(claim.executor_key)
        return await executor.execute(claim)

    async def cancel(self, claim: TaskClaim) -> None:
        """Request provider-side cancellation when the adapter supports it."""

        executor = self._get(claim.executor_key)
        if isinstance(executor, CancellableTaskExecutor):
            await executor.cancel(claim)

    def _get(self, key: str) -> TaskExecutor:
        try:
            return self._executors[key]
        except KeyError as exc:
            raise ExecutorNotFoundError(f"executor is not registered: {key}") from exc

    @classmethod
    def from_entry_points(
        cls, discovered: Iterable[ExecutorEntryPoint] | None = None
    ) -> "ExecutorRegistry":
        """Load no-argument executor factories installed under the public plugin group."""

        entries = discovered
        if entries is None:
            entries = entry_points(group=EXECUTOR_ENTRY_POINT_GROUP)
        registry = cls()
        for entry in entries:
            factory = entry.load()
            if not callable(factory):
                raise ExecutorRegistrationError(
                    f"executor entry point must load a callable factory: {entry.name}"
                )
            executor = factory()
            if not isinstance(executor, TaskExecutor):
                raise ExecutorRegistrationError(
                    f"executor factory returned an invalid adapter: {entry.name}"
                )
            registry.register(entry.name, executor)
        return registry
