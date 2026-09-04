"""Deterministic executor available only to the disposable system smoke environment."""

import os

from jb_orchestrator.worker import TaskClaim, TaskResult
from jb_orchestrator.workflows import NodeOutcome


class SystemSmokeExecutor:
    async def execute(self, claim: TaskClaim) -> TaskResult:
        """Return a stable artifact without contacting an external agent runtime."""

        return TaskResult(
            outcome=NodeOutcome.SUCCESS,
            output={
                "node_key": claim.node_key,
                "summary": "system smoke task completed",
            },
        )


def create_executor() -> SystemSmokeExecutor:
    """Fail closed when the fixture is accidentally installed outside tests."""

    if os.environ.get("JB_ENVIRONMENT") != "test":
        raise RuntimeError("system-smoke executor requires JB_ENVIRONMENT=test")
    return SystemSmokeExecutor()
