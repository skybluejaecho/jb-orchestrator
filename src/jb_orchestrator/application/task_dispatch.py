"""Transactional task claiming and lease coordination."""

from collections.abc import Callable, Collection
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.output_contracts import enforce_output_contract
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.artifacts import TaskArtifact
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.worker.models import (
    TaskArtifactInput,
    TaskClaim,
    TaskContextEnvelope,
    TaskResult,
)
from jb_orchestrator.workflows import WorkflowEngine, WorkflowExecution, WorkflowExecutionError


class TaskDispatchService:
    """Coordinate worker leases without executing non-deterministic work in a transaction."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        engine: WorkflowEngine | None = None,
        *,
        lease_grace_seconds: int = 30,
    ) -> None:
        if lease_grace_seconds < 1:
            raise ValueError("lease_grace_seconds must be greater than zero")
        self._unit_of_work_factory = unit_of_work_factory
        self._engine = engine or WorkflowEngine()
        self._lease_grace_seconds = lease_grace_seconds

    async def claim_next(
        self,
        worker_id: str,
        executor_keys: Collection[str] | None = None,
        *,
        at: datetime | None = None,
    ) -> TaskClaim | None:
        changed_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            candidate = await unit_of_work.workflow_executions.get_ready_for_update(executor_keys)
            if candidate is None:
                return None
            execution = candidate.execution
            definition = execution.snapshot.node(candidate.node_key)
            phase_pack = (
                execution.snapshot.phase_pack(definition.phase_pack)
                if definition.phase_pack is not None
                else None
            )
            upstream_artifacts, named_inputs = await self._resolve_artifact_inputs(
                unit_of_work, execution, candidate.node_key
            )
            node = self._engine.claim_task(
                execution,
                candidate.node_key,
                worker_id=worker_id,
                lease_seconds=definition.timeout_seconds + self._lease_grace_seconds,
                at=changed_at,
            )
            if node.lease_token is None:
                raise RuntimeError("claimed node did not receive a lease token")
            request_context = execution.snapshot.request_context
            skill_references = set(definition.skills)
            if phase_pack is not None:
                skill_references.update(phase_pack.skills)
            claim = TaskClaim(
                execution_id=execution.id,
                run_id=execution.snapshot.run_id,
                node_key=node.node_key,
                executor_key=node.executor_key,
                worker_id=worker_id,
                lease_token=node.lease_token,
                idempotency_key=f"{execution.id}:{node.node_key}:{node.visit_count}",
                visit_count=node.visit_count,
                attempt_count=node.attempt_count,
                timeout_seconds=definition.timeout_seconds,
                workflow_key=execution.snapshot.definition_key,
                workflow_version=execution.snapshot.definition_version,
                instructions=definition.instructions,
                configuration=dict(definition.configuration),
                skills=tuple(
                    execution.snapshot.skill(reference)
                    for reference in sorted(
                        skill_references, key=lambda value: (value.key, value.version)
                    )
                ),
                phase_pack=phase_pack,
                context=(
                    TaskContextEnvelope(
                        request=request_context,
                        upstream_artifacts=tuple(upstream_artifacts),
                        named_inputs=named_inputs,
                    )
                    if request_context is not None
                    else None
                ),
                model_selection=execution.snapshot.model_selection(node.node_key),
            )
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "task.claimed",
                node_key=node.node_key,
                worker_id=worker_id,
                lease_token=str(node.lease_token),
                attempt=node.attempt_count,
            )
            await unit_of_work.commit()
        return claim

    @staticmethod
    async def _resolve_artifact_inputs(
        unit_of_work: UnitOfWork,
        execution: WorkflowExecution,
        node_key: str,
    ) -> tuple[list[TaskArtifact], tuple[TaskArtifactInput, ...]]:
        node = execution.snapshot.node(node_key)
        if node.phase_pack is None:
            artifacts = await unit_of_work.artifacts.list_latest_for_nodes(
                execution.id, execution.snapshot.incoming_sources(node_key)
            )
            return artifacts, ()

        phase_pack = execution.snapshot.phase_pack(node.phase_pack)
        source_nodes = {value.source_node for value in node.input_mappings}
        artifacts = await unit_of_work.artifacts.list_latest_for_nodes(execution.id, source_nodes)
        artifacts_by_node = {value.producer_node_key: value for value in artifacts}
        inputs = tuple(
            TaskArtifactInput(
                name=mapping.input_key,
                artifact=artifacts_by_node[mapping.source_node],
            )
            for mapping in node.input_mappings
            if mapping.source_node in artifacts_by_node
        )
        required = {value.key for value in phase_pack.inputs if value.required}
        missing = sorted(required - {value.name for value in inputs})
        if missing:
            raise WorkflowExecutionError(
                f"task {node_key} is missing required artifact inputs: {', '.join(missing)}"
            )
        return artifacts, inputs

    async def heartbeat(self, claim: TaskClaim, *, at: datetime | None = None) -> WorkflowExecution:
        changed_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, claim.execution_id)
            definition = execution.snapshot.node(claim.node_key)
            self._engine.renew_lease(
                execution,
                claim.node_key,
                claim.lease_token,
                lease_seconds=definition.timeout_seconds + self._lease_grace_seconds,
                at=changed_at,
            )
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "task.lease_renewed",
                node_key=claim.node_key,
                worker_id=claim.worker_id,
            )
            await unit_of_work.commit()
        return execution

    async def complete(
        self,
        claim: TaskClaim,
        result: TaskResult,
        *,
        at: datetime | None = None,
    ) -> WorkflowExecution:
        changed_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, claim.execution_id)
            definition = execution.snapshot.node(claim.node_key)
            phase_pack = (
                execution.snapshot.phase_pack(definition.phase_pack)
                if definition.phase_pack is not None
                else None
            )
            decision = enforce_output_contract(
                phase_pack,
                result.outcome,
                result.output,
            )
            self._engine.complete_task(
                execution,
                claim.node_key,
                decision.outcome,
                output=decision.output,
                lease_token=claim.lease_token,
                at=changed_at,
            )
            artifact = TaskArtifact(
                execution_id=execution.id,
                producer_node_key=claim.node_key,
                visit_count=claim.visit_count,
                outcome=decision.outcome,
                content=decision.output,
                created_at=changed_at,
            )
            await unit_of_work.artifacts.add(artifact)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "task.completed",
                node_key=claim.node_key,
                worker_id=claim.worker_id,
                outcome=decision.outcome.value,
                artifact_id=str(artifact.id),
                output_contract_rejected=decision.rejected,
            )
            await unit_of_work.commit()
        return execution

    async def fail(
        self,
        claim: TaskClaim,
        reason: str,
        *,
        at: datetime | None = None,
    ) -> WorkflowExecution:
        changed_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._get_execution(unit_of_work, claim.execution_id)
            self._engine.fail_task(
                execution,
                claim.node_key,
                reason,
                lease_token=claim.lease_token,
                at=changed_at,
            )
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "task.failed",
                node_key=claim.node_key,
                worker_id=claim.worker_id,
                reason=reason,
            )
            await unit_of_work.commit()
        return execution

    async def recover_expired(self, *, at: datetime | None = None) -> bool:
        changed_at = at or datetime.now(UTC)
        async with self._unit_of_work_factory() as unit_of_work:
            candidate = await unit_of_work.workflow_executions.get_expired_for_update(changed_at)
            if candidate is None:
                return False
            execution = candidate.execution
            node = execution.nodes[candidate.node_key]
            expired_worker_id = node.worker_id
            self._engine.expire_task(execution, candidate.node_key, at=changed_at)
            await unit_of_work.workflow_executions.save(execution)
            await self._append_event(
                unit_of_work,
                execution,
                "task.lease_expired",
                node_key=candidate.node_key,
                worker_id=expired_worker_id,
            )
            await unit_of_work.commit()
        return True

    @staticmethod
    async def _get_execution(unit_of_work: UnitOfWork, execution_id: UUID) -> WorkflowExecution:
        execution = await unit_of_work.workflow_executions.get_for_update(execution_id)
        if execution is None:
            raise ResourceNotFound(f"workflow execution not found: {execution_id}")
        return execution

    @staticmethod
    async def _append_event(
        unit_of_work: UnitOfWork,
        execution: WorkflowExecution,
        event_type: str,
        **payload: Any,
    ) -> None:
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="workflow_execution",
                aggregate_id=execution.id,
                event_type=event_type,
                payload={"status": execution.status.value, **payload},
            )
        )
