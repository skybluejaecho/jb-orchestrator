"""Shared heartbeat wrapper for long-running worker processes."""

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any, TypeVar

from jb_orchestrator.application.worker_presence_services import WorkerPresenceService
from jb_orchestrator.worker_presence.models import WorkerInstance, WorkerKind

T = TypeVar("T")


class WorkerPresenceRuntime:
    def __init__(
        self,
        service: WorkerPresenceService,
        *,
        worker_id: str,
        kind: WorkerKind,
        hostname: str,
        process_id: int,
        capabilities: tuple[str, ...],
        workspace_scope: str | None = None,
        heartbeat_interval_seconds: float = 30.0,
    ) -> None:
        if heartbeat_interval_seconds <= 0:
            raise ValueError("worker presence heartbeat interval must be positive")
        self._service = service
        self._worker_id = worker_id
        self._kind = kind
        self._hostname = hostname
        self._process_id = process_id
        self._capabilities = capabilities
        self._workspace_scope = workspace_scope
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    async def run(self, operation: Callable[[], Coroutine[Any, Any, T]]) -> T:
        worker = await self._service.register(
            worker_id=self._worker_id,
            kind=self._kind,
            hostname=self._hostname,
            process_id=self._process_id,
            capabilities=self._capabilities,
            workspace_scope=self._workspace_scope,
        )
        operation_task: asyncio.Task[T] = asyncio.create_task(
            operation(), name=f"worker:{worker.id}"
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {operation_task},
                    timeout=self._heartbeat_interval_seconds,
                )
                if operation_task in done:
                    return operation_task.result()
                await self._service.heartbeat(worker.id)
        finally:
            await self._cancel(operation_task)
            await self._stop(worker)

    @staticmethod
    async def _cancel(task: asyncio.Task[object]) -> None:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    async def _stop(self, worker: WorkerInstance) -> None:
        with suppress(Exception):
            await self._service.stop(worker.id)
