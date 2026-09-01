"""Database-backed worker polling runtime."""

import asyncio
from contextlib import suppress

from jb_orchestrator.application.task_dispatch import TaskDispatchService
from jb_orchestrator.worker.registry import ExecutorRegistry


class WorkerRuntime:
    """Lease one task, execute it outside a transaction, and persist its result."""

    def __init__(
        self,
        worker_id: str,
        dispatch: TaskDispatchService,
        executors: ExecutorRegistry,
        *,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        self._worker_id = worker_id
        self._dispatch = dispatch
        self._executors = executors
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> bool:
        await self._dispatch.recover_expired()
        claim = await self._dispatch.claim_next(self._worker_id, self._executors.supported_keys)
        if claim is None:
            return False
        try:
            result = await asyncio.wait_for(
                self._executors.execute(claim), timeout=claim.timeout_seconds
            )
        except TimeoutError:
            await self._dispatch.fail(claim, "executor timed out")
        except Exception as exc:
            await self._dispatch.fail(claim, f"executor failed: {exc}")
        else:
            await self._dispatch.complete(claim, result)
        return True

    async def run(self, stop: asyncio.Event) -> None:
        """Poll until the caller requests a graceful stop."""

        while not stop.is_set():
            worked = await self.run_once()
            if worked:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval_seconds)
