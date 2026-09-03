"""Synchronize workflow outcomes with their parent run and request."""

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent, RequestStatus, RunStatus
from jb_orchestrator.workflows import WorkflowExecution, WorkflowStatus

RUN_STATUS_BY_WORKFLOW = {
    WorkflowStatus.PENDING: RunStatus.QUEUED,
    WorkflowStatus.RUNNING: RunStatus.RUNNING,
    WorkflowStatus.AWAITING_APPROVAL: RunStatus.AWAITING_APPROVAL,
    WorkflowStatus.SUCCEEDED: RunStatus.SUCCEEDED,
    WorkflowStatus.FAILED: RunStatus.FAILED,
    WorkflowStatus.CANCELLED: RunStatus.CANCELLED,
}


async def synchronize_execution_lifecycle(
    unit_of_work: UnitOfWork, execution: WorkflowExecution
) -> None:
    """Persist parent lifecycle changes in the execution transition transaction."""

    if execution.snapshot.request_context is None:
        return

    run = await unit_of_work.runs.get_for_update(execution.snapshot.run_id)
    if run is None:
        raise ResourceNotFound(f"run not found: {execution.snapshot.run_id}")
    request = await unit_of_work.requests.get_for_update(run.request_id)
    if request is None:
        raise ResourceNotFound(f"request not found: {run.request_id}")

    target = RUN_STATUS_BY_WORKFLOW[execution.status]
    if run.status is not target:
        previous = run.status
        if target is RunStatus.FAILED:
            run.fail(
                execution.failure_reason or "workflow execution failed", at=execution.updated_at
            )
        else:
            run.transition_to(target, at=execution.updated_at)
        await unit_of_work.runs.save(run)
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="run",
                aggregate_id=run.id,
                event_type="run.status_changed",
                payload={
                    "from": previous.value,
                    "to": run.status.value,
                    "workflow_execution_id": str(execution.id),
                },
            )
        )

    if execution.status is WorkflowStatus.SUCCEEDED and request.status is RequestStatus.ACTIVE:
        request.complete(at=execution.updated_at)
        await unit_of_work.requests.save(request)
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="request",
                aggregate_id=request.id,
                event_type="request.completed",
                payload={"run_id": str(run.id), "workflow_execution_id": str(execution.id)},
            )
        )
    elif execution.status is WorkflowStatus.CANCELLED and request.status in {
        RequestStatus.RECEIVED,
        RequestStatus.ACTIVE,
    }:
        request.cancel(at=execution.updated_at)
        await unit_of_work.requests.save(request)
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="request",
                aggregate_id=request.id,
                event_type="request.cancelled",
                payload={"run_id": str(run.id), "workflow_execution_id": str(execution.id)},
            )
        )
