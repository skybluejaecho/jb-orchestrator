"""Database-backed worker polling runtime."""

import asyncio
from contextlib import suppress
from dataclasses import replace

from jb_orchestrator.application.budget_services import BudgetService, BudgetUsageRequired
from jb_orchestrator.application.task_dispatch import TaskDispatchService
from jb_orchestrator.budgets import BudgetLimitExceeded, BudgetReservation
from jb_orchestrator.skills.materialization import SkillMaterializationError, SkillMaterializer
from jb_orchestrator.worker.models import TaskClaim, TaskResult
from jb_orchestrator.worker.registry import ExecutorRegistry
from jb_orchestrator.workflows import NodeExecutionStatus


class ExecutorHeartbeatError(RuntimeError):
    """Raised when lease ownership can no longer be renewed safely."""


class WorkerStopRequested(RuntimeError):
    """Raised after an active executor is cancelled for graceful worker shutdown."""


class WorkerRuntime:
    """Lease one task, execute it outside a transaction, and persist its result."""

    def __init__(
        self,
        worker_id: str,
        dispatch: TaskDispatchService,
        executors: ExecutorRegistry,
        *,
        poll_interval_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 30.0,
        cancellation_timeout_seconds: float = 10.0,
        skill_materializer: SkillMaterializer | None = None,
        budget_service: BudgetService | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be greater than zero")
        if cancellation_timeout_seconds <= 0:
            raise ValueError("cancellation_timeout_seconds must be greater than zero")
        self._worker_id = worker_id
        self._dispatch = dispatch
        self._executors = executors
        self._poll_interval_seconds = poll_interval_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._cancellation_timeout_seconds = cancellation_timeout_seconds
        self._skill_materializer = skill_materializer
        self._budget_service = budget_service

    async def run_once(self, stop: asyncio.Event | None = None) -> bool:
        await self._dispatch.recover_expired()
        claim = await self._dispatch.claim_next(self._worker_id, self._executors.supported_keys)
        if claim is None:
            return False
        reservation: BudgetReservation | None = None
        try:
            if claim.skills:
                if self._skill_materializer is None:
                    raise SkillMaterializationError("worker has no skill materializer configured")
                materialized = await self._skill_materializer.materialize_all(claim.skills)
                claim = replace(
                    claim,
                    skill_paths={
                        f"{skill.key}@{skill.version}": str(skill.entrypoint_path)
                        for skill in materialized
                    },
                )
            if self._budget_service is not None:
                reservation = await self._budget_service.reserve(claim)
            result = await self._execute_with_lease(claim, stop)
            if self._budget_service is not None:
                await self._budget_service.settle(claim, reservation, result.usage)
        except SkillMaterializationError as exc:
            await self._fail(claim, f"skill materialization failed: {exc}", reservation)
        except BudgetLimitExceeded as exc:
            await self._fail(claim, f"budget reservation failed: {exc}", reservation)
        except BudgetUsageRequired as exc:
            await self._fail(claim, f"budget settlement failed: {exc}", reservation)
        except TimeoutError as exc:
            await self._fail(claim, str(exc) or "executor timed out", reservation)
        except ExecutorHeartbeatError as exc:
            await self._fail(claim, str(exc), reservation)
        except WorkerStopRequested as exc:
            await self._fail(claim, str(exc), reservation)
        except asyncio.CancelledError:
            await self._fail(claim, "worker runtime cancelled", reservation)
            raise
        except Exception as exc:
            await self._fail(claim, f"executor failed: {exc}", reservation)
        else:
            await self._dispatch.complete(claim, result)
        return True

    async def _execute_with_lease(
        self,
        claim: TaskClaim,
        stop: asyncio.Event | None,
    ) -> TaskResult:
        execution_task = asyncio.create_task(
            self._executors.execute(claim),
            name=f"executor:{claim.execution_id}:{claim.node_key}",
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat(claim),
            name=f"heartbeat:{claim.execution_id}:{claim.node_key}",
        )
        stop_task = (
            asyncio.create_task(stop.wait(), name=f"stop:{claim.execution_id}:{claim.node_key}")
            if stop is not None
            else None
        )
        monitors: set[asyncio.Task[object]] = {execution_task, heartbeat_task}
        if stop_task is not None:
            monitors.add(stop_task)

        try:
            done, _ = await asyncio.wait(
                monitors,
                timeout=claim.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                try:
                    heartbeat_task.result()
                except Exception as exc:
                    cancellation_error = await self._cancel_executor(claim, execution_task)
                    reason = f"executor heartbeat failed: {exc}"
                    raise ExecutorHeartbeatError(
                        self._with_cancellation_error(reason, cancellation_error)
                    ) from exc
                raise ExecutorHeartbeatError("executor heartbeat stopped unexpectedly")
            if execution_task in done:
                return execution_task.result()
            if stop_task is not None and stop_task in done:
                cancellation_error = await self._cancel_executor(claim, execution_task)
                raise WorkerStopRequested(
                    self._with_cancellation_error(
                        "worker stop requested during executor run",
                        cancellation_error,
                    )
                )
            cancellation_error = await self._cancel_executor(claim, execution_task)
            raise TimeoutError(
                self._with_cancellation_error("executor timed out", cancellation_error)
            )
        except asyncio.CancelledError:
            await self._cancel_executor(claim, execution_task)
            raise
        finally:
            await self._cancel_monitor(heartbeat_task)
            if stop_task is not None:
                await self._cancel_monitor(stop_task)

    async def _heartbeat(self, claim: TaskClaim) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval_seconds)
            await self._dispatch.heartbeat(claim)

    async def _cancel_executor(
        self,
        claim: TaskClaim,
        execution_task: asyncio.Task[object],
    ) -> str | None:
        if not execution_task.done():
            execution_task.cancel()
        provider_cancel_task = asyncio.create_task(
            self._executors.cancel(claim),
            name=f"cancel:{claim.execution_id}:{claim.node_key}",
        )
        done, _ = await asyncio.wait(
            {execution_task, provider_cancel_task},
            timeout=self._cancellation_timeout_seconds,
        )
        errors: list[str] = []
        if execution_task not in done:
            errors.append("local executor task did not stop before cancellation timeout")
        else:
            with suppress(asyncio.CancelledError, Exception):
                execution_task.result()
        if provider_cancel_task not in done:
            provider_cancel_task.cancel()
            with suppress(asyncio.CancelledError):
                await provider_cancel_task
            errors.append("provider cancellation timed out")
        else:
            try:
                provider_cancel_task.result()
            except asyncio.CancelledError:
                errors.append("provider cancellation was cancelled")
            except Exception as exc:
                errors.append(f"provider cancellation failed: {exc}")
        return "; ".join(errors) or None

    @staticmethod
    async def _cancel_monitor(task: asyncio.Task[object]) -> None:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    @staticmethod
    def _with_cancellation_error(reason: str, cancellation_error: str | None) -> str:
        return f"{reason}; {cancellation_error}" if cancellation_error else reason

    async def _fail(
        self,
        claim: TaskClaim,
        reason: str,
        reservation: BudgetReservation | None,
    ) -> None:
        execution = await self._dispatch.fail(claim, reason)
        if (
            execution.nodes[claim.node_key].status is NodeExecutionStatus.FAILED
            and self._budget_service is not None
        ):
            await self._budget_service.forfeit(claim, reservation)

    async def run(self, stop: asyncio.Event) -> None:
        """Poll until the caller requests a graceful stop."""

        while not stop.is_set():
            worked = await self.run_once(stop)
            if worked:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval_seconds)
