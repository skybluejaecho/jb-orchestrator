from uuid import UUID

import pytest
from jb_system_smoke_executor import SystemSmokeExecutor, create_executor

from jb_orchestrator.worker import TaskClaim
from jb_orchestrator.workflows import NodeOutcome


def test_smoke_executor_is_available_only_in_test_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JB_ENVIRONMENT", "local")

    with pytest.raises(RuntimeError, match="JB_ENVIRONMENT=test"):
        create_executor()

    monkeypatch.setenv("JB_ENVIRONMENT", "test")
    assert isinstance(create_executor(), SystemSmokeExecutor)


async def test_smoke_executor_returns_a_stable_success_artifact() -> None:
    claim = TaskClaim(
        execution_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        node_key="work",
        executor_key="system-smoke",
        worker_id="system-smoke-worker",
        visit_count=1,
        attempt_count=1,
        lease_token=UUID("00000000-0000-0000-0000-000000000003"),
        idempotency_key="smoke:work:1",
        timeout_seconds=30,
        workflow_key="system-smoke",
        workflow_version=1,
        instructions=None,
        configuration={},
        skills=(),
    )

    result = await SystemSmokeExecutor().execute(claim)

    assert result.outcome is NodeOutcome.SUCCESS
    assert result.output == {
        "node_key": "work",
        "summary": "system smoke task completed",
    }
