"""SQLAlchemy workflow persistence adapters."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import (
    NodeExecutionRecord,
    WorkflowDefinitionRecord,
    WorkflowExecutionRecord,
)
from jb_orchestrator.workflows.models import (
    NodeExecution,
    NodeExecutionStatus,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowTaskCandidate,
)
from jb_orchestrator.workflows.serialization import (
    definition_from_dict,
    definition_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)


def node_record(node: NodeExecution) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        id=node.id,
        workflow_execution_id=node.workflow_execution_id,
        node_key=node.node_key,
        status=node.status,
        visit_count=node.visit_count,
        attempt_count=node.attempt_count,
        outcome=node.outcome,
        output=node.output,
        worker_id=node.worker_id,
        lease_token=node.lease_token,
        lease_expires_at=node.lease_expires_at,
        started_at=node.started_at,
        completed_at=node.completed_at,
        updated_at=node.updated_at,
    )


def node_from_record(record: NodeExecutionRecord) -> NodeExecution:
    return NodeExecution(
        id=record.id,
        workflow_execution_id=record.workflow_execution_id,
        node_key=record.node_key,
        status=record.status,
        visit_count=record.visit_count,
        attempt_count=record.attempt_count,
        outcome=record.outcome,
        output=record.output,
        worker_id=record.worker_id,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
    )


class SqlAlchemyWorkflowDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, definition: WorkflowDefinition) -> None:
        self._session.add(
            WorkflowDefinitionRecord(
                id=definition.id,
                key=definition.key,
                version=definition.version,
                definition=definition_to_dict(definition),
            )
        )

    async def get(self, key: str, version: int | None = None) -> WorkflowDefinition | None:
        statement = select(WorkflowDefinitionRecord).where(WorkflowDefinitionRecord.key == key)
        if version is None:
            statement = statement.order_by(WorkflowDefinitionRecord.version.desc()).limit(1)
        else:
            statement = statement.where(WorkflowDefinitionRecord.version == version)
        record = await self._session.scalar(statement)
        return definition_from_dict(record.definition) if record is not None else None


class SqlAlchemyWorkflowExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, execution: WorkflowExecution) -> None:
        self._session.add(
            WorkflowExecutionRecord(
                id=execution.id,
                run_id=execution.snapshot.run_id,
                snapshot=snapshot_to_dict(execution.snapshot),
                status=execution.status,
                failure_reason=execution.failure_reason,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                updated_at=execution.updated_at,
                version=execution.version,
                nodes=[node_record(node) for node in execution.nodes.values()],
            )
        )

    async def get(self, execution_id: UUID) -> WorkflowExecution | None:
        record = await self._session.get(WorkflowExecutionRecord, execution_id)
        return await self._to_execution(record)

    async def get_by_run(self, run_id: UUID) -> WorkflowExecution | None:
        record = await self._session.scalar(
            select(WorkflowExecutionRecord).where(WorkflowExecutionRecord.run_id == run_id)
        )
        return await self._to_execution(record)

    async def get_ready_for_update(self) -> WorkflowTaskCandidate | None:
        node = await self._session.scalar(
            select(NodeExecutionRecord)
            .join(WorkflowExecutionRecord)
            .where(
                NodeExecutionRecord.status == NodeExecutionStatus.READY,
                WorkflowExecutionRecord.status == WorkflowStatus.RUNNING,
            )
            .order_by(NodeExecutionRecord.updated_at, NodeExecutionRecord.id)
            .with_for_update(skip_locked=True, of=NodeExecutionRecord)
            .limit(1)
        )
        return await self._candidate(node)

    async def get_expired_for_update(self, at: datetime) -> WorkflowTaskCandidate | None:
        node = await self._session.scalar(
            select(NodeExecutionRecord)
            .join(WorkflowExecutionRecord)
            .where(
                NodeExecutionRecord.status == NodeExecutionStatus.RUNNING,
                NodeExecutionRecord.lease_expires_at.is_not(None),
                NodeExecutionRecord.lease_expires_at <= at,
                WorkflowExecutionRecord.status == WorkflowStatus.RUNNING,
            )
            .order_by(NodeExecutionRecord.lease_expires_at, NodeExecutionRecord.id)
            .with_for_update(skip_locked=True, of=NodeExecutionRecord)
            .limit(1)
        )
        return await self._candidate(node)

    async def _candidate(self, node: NodeExecutionRecord | None) -> WorkflowTaskCandidate | None:
        if node is None:
            return None
        record = await self._session.get(WorkflowExecutionRecord, node.workflow_execution_id)
        execution = await self._to_execution(record)
        if execution is None:
            return None
        return WorkflowTaskCandidate(execution=execution, node_key=node.node_key)

    async def _to_execution(
        self, record: WorkflowExecutionRecord | None
    ) -> WorkflowExecution | None:
        if record is None:
            return None
        node_records = await self._session.scalars(
            select(NodeExecutionRecord).where(
                NodeExecutionRecord.workflow_execution_id == record.id
            )
        )
        nodes = [node_from_record(node) for node in node_records]
        return WorkflowExecution(
            id=record.id,
            snapshot=snapshot_from_dict(record.snapshot),
            status=record.status,
            nodes={node.node_key: node for node in nodes},
            failure_reason=record.failure_reason,
            started_at=record.started_at,
            completed_at=record.completed_at,
            updated_at=record.updated_at,
            version=record.version,
        )

    async def save(self, execution: WorkflowExecution) -> None:
        record = await self._session.get(WorkflowExecutionRecord, execution.id)
        if record is None:
            await self.add(execution)
            return
        record.status = execution.status
        record.failure_reason = execution.failure_reason
        record.started_at = execution.started_at
        record.completed_at = execution.completed_at
        record.updated_at = execution.updated_at
        record.version = execution.version

        stored_nodes = await self._session.scalars(
            select(NodeExecutionRecord).where(
                NodeExecutionRecord.workflow_execution_id == execution.id
            )
        )
        records_by_key = {node.node_key: node for node in stored_nodes}
        for node in execution.nodes.values():
            node_state = records_by_key.get(node.node_key)
            if node_state is None:
                self._session.add(node_record(node))
                continue
            node_state.status = node.status
            node_state.visit_count = node.visit_count
            node_state.attempt_count = node.attempt_count
            node_state.outcome = node.outcome
            node_state.output = node.output
            node_state.worker_id = node.worker_id
            node_state.lease_token = node.lease_token
            node_state.lease_expires_at = node.lease_expires_at
            node_state.started_at = node.started_at
            node_state.completed_at = node.completed_at
            node_state.updated_at = node.updated_at
