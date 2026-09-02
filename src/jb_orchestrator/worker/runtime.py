"""Database-backed worker polling runtime."""

import asyncio
from contextlib import suppress
from dataclasses import replace

from jb_orchestrator.application.budget_services import BudgetService, BudgetUsageRequired
from jb_orchestrator.application.task_dispatch import TaskDispatchService
from jb_orchestrator.budgets import BudgetLimitExceeded, BudgetReservation
from jb_orchestrator.skills.materialization import SkillMaterializationError, SkillMaterializer
from jb_orchestrator.worker.models import TaskClaim
from jb_orchestrator.worker.registry import ExecutorRegistry
from jb_orchestrator.workflows import NodeExecutionStatus


class WorkerRuntime:
    """Lease one task, execute it outside a transaction, and persist its result."""

    def __init__(
        self,
        worker_id: str,
        dispatch: TaskDispatchService,
        executors: ExecutorRegistry,
        *,
        poll_interval_seconds: float = 1.0,
        skill_materializer: SkillMaterializer | None = None,
        budget_service: BudgetService | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        self._worker_id = worker_id
        self._dispatch = dispatch
        self._executors = executors
        self._poll_interval_seconds = poll_interval_seconds
        self._skill_materializer = skill_materializer
        self._budget_service = budget_service

    async def run_once(self) -> bool:
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
            result = await asyncio.wait_for(
                self._executors.execute(claim), timeout=claim.timeout_seconds
            )
            if self._budget_service is not None:
                await self._budget_service.settle(claim, reservation, result.usage)
        except SkillMaterializationError as exc:
            await self._fail(claim, f"skill materialization failed: {exc}", reservation)
        except BudgetLimitExceeded as exc:
            await self._fail(claim, f"budget reservation failed: {exc}", reservation)
        except BudgetUsageRequired as exc:
            await self._fail(claim, f"budget settlement failed: {exc}", reservation)
        except TimeoutError:
            await self._fail(claim, "executor timed out", reservation)
        except Exception as exc:
            await self._fail(claim, f"executor failed: {exc}", reservation)
        else:
            await self._dispatch.complete(claim, result)
        return True

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
            worked = await self.run_once()
            if worked:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval_seconds)
