from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from jb_orchestrator.api.main import create_app
from jb_orchestrator.application import ExternalExecutionService
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.worker import TaskClaim
from tests.support import MemoryStore, MemoryUnitOfWork


def task_claim(*, key: str) -> TaskClaim:
    return TaskClaim(
        execution_id=uuid4(),
        run_id=uuid4(),
        node_key="review",
        executor_key="openclaw",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key=key,
        visit_count=1,
        attempt_count=1,
        timeout_seconds=300,
        workflow_key="delivery",
        workflow_version=1,
        instructions="Review the implementation.",
        configuration={},
        skills=(),
    )


async def test_external_execution_list_supports_polling_filters() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    active_claim = task_claim(key="execution:review:active")
    starting_claim = task_claim(key="execution:review:starting")
    active = await service.prepare(active_claim, session_key="agent:active", agent_id="reviewer")
    await service.accept(active_claim.idempotency_key, "openclaw-run-1")
    await service.prepare(starting_claim, session_key="agent:starting", agent_id=None)
    app = create_app(external_execution_service=service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/v1/external-executions",
            params={"run_id": str(active_claim.run_id), "status": "active"},
        )
        invalid_limit = await client.get("/v1/external-executions", params={"limit": 0})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(active.id)]
    assert response.json()[0]["external_run_id"] == "openclaw-run-1"
    assert response.json()[0]["workspace_path"] is None
    assert invalid_limit.status_code == 422


async def test_external_execution_detail_and_missing_problem() -> None:
    store = MemoryStore()
    service = ExternalExecutionService(lambda: MemoryUnitOfWork(store))
    claim = task_claim(key="execution:review:detail")
    execution = await service.prepare(
        claim,
        session_key="agent:detail",
        agent_id=None,
        workspace_path="C:/worktrees/review",
        workspace_repository_path="C:/projects/delivery",
        workspace_branch="jb/execution/review-v1",
        workspace_base_ref="develop",
    )
    await service.finish(
        claim.idempotency_key,
        ExternalExecutionStatus.FAILED,
        failure_reason="gateway disconnected",
    )
    app = create_app(external_execution_service=service)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/external-executions/{execution.id}")
        missing = await client.get(f"/v1/external-executions/{UUID(int=0)}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["failure_reason"] == "gateway disconnected"
    assert response.json()["workspace_branch"] == "jb/execution/review-v1"
    assert response.json()["workspace_repository_path"] == "C:/projects/delivery"
    assert missing.status_code == 404
    assert missing.json()["title"] == "Resource not found"
