"""OpenClaw implementation of the JB executor ports."""

import json
from typing import Any

from jb_openclaw_executor.bridge import OpenClawBridge
from jb_orchestrator.application.external_execution_services import ExternalExecutionService
from jb_orchestrator.domain.exceptions import InvalidStateTransition
from jb_orchestrator.external_executions import ExternalExecution, ExternalExecutionStatus
from jb_orchestrator.worker import TaskClaim, TaskResult, TokenUsage
from jb_orchestrator.workflows import NodeOutcome

SUCCESS_STATUSES = frozenset({"ok", "success", "succeeded", "completed"})


class OpenClawExecutor:
    def __init__(self, service: ExternalExecutionService, bridge: OpenClawBridge) -> None:
        self._service = service
        self._bridge = bridge

    async def execute(self, claim: TaskClaim) -> TaskResult:
        agent_id = self._optional_string(claim.configuration, "agent_id")
        session_key = self._optional_string(claim.configuration, "session_key") or (
            f"agent:{agent_id or 'main'}:jb:{claim.execution_id}:{claim.node_key}"
        )
        execution = await self._service.prepare(claim, session_key=session_key, agent_id=agent_id)
        if execution.is_terminal:
            return self._stored_result(execution)
        if execution.external_run_id is None:
            accepted = await self._bridge.start(self._start_request(claim, execution))
            external_run_id = accepted.get("runId")
            if not isinstance(external_run_id, str) or not external_run_id:
                raise RuntimeError("OpenClaw agent response did not include runId")
            execution = await self._service.accept(claim.idempotency_key, external_run_id)

        if execution.external_run_id is None:
            raise RuntimeError("active OpenClaw execution has no runId")
        terminal = await self._bridge.wait(execution.external_run_id, claim.timeout_seconds * 1_000)
        status = str(terminal.get("status", "unknown")).lower()
        if status == "timeout":
            await self._bridge.cancel(execution.external_run_id)
            await self._service.finish(
                claim.idempotency_key,
                ExternalExecutionStatus.CANCELLED,
                terminal_result=terminal,
                failure_reason="OpenClaw agent.wait timed out",
            )
            raise TimeoutError("OpenClaw agent.wait timed out and the run was cancelled")
        succeeded = status in SUCCESS_STATUSES
        external_status = (
            ExternalExecutionStatus.SUCCEEDED
            if succeeded
            else (
                ExternalExecutionStatus.CANCELLED
                if status in {"cancelled", "canceled"}
                else ExternalExecutionStatus.FAILED
            )
        )
        await self._service.finish(
            claim.idempotency_key,
            external_status,
            terminal_result=terminal,
            failure_reason=None if succeeded else self._failure_reason(terminal),
        )
        return self._result(execution, terminal, succeeded=succeeded)

    async def cancel(self, claim: TaskClaim) -> None:
        execution = await self._service.get(claim.idempotency_key)
        if execution is None or execution.is_terminal or execution.external_run_id is None:
            return
        await self._bridge.cancel(execution.external_run_id)
        try:
            await self._service.finish(
                claim.idempotency_key,
                ExternalExecutionStatus.CANCELLED,
                failure_reason="OpenClaw execution cancelled by worker",
            )
        except InvalidStateTransition:
            # A terminal result won a cancellation race while the abort request was in flight.
            return

    def _start_request(self, claim: TaskClaim, execution: ExternalExecution) -> dict[str, Any]:
        request: dict[str, Any] = {
            "message": self._prompt(claim),
            "sessionKey": execution.external_session_key,
            "idempotencyKey": claim.idempotency_key,
            "timeoutSeconds": claim.timeout_seconds,
        }
        optional = {
            "agentId": execution.external_agent_id,
            "cwd": self._optional_string(claim.configuration, "cwd"),
            "thinking": self._optional_string(claim.configuration, "thinking"),
        }
        request.update({key: value for key, value in optional.items() if value is not None})
        if claim.model_selection is not None:
            request["provider"] = claim.model_selection.profile.provider
            request["model"] = claim.model_selection.profile.model_id
        return request

    @staticmethod
    def _prompt(claim: TaskClaim) -> str:
        instructions = claim.instructions or "Complete the assigned workflow task."
        sections = [f"Task instructions:\n{instructions}"]
        if claim.context is not None:
            request = claim.context.request
            sections.append(f"Original user request:\n{request.prompt}")
            sections.append(
                "Project context:\n"
                f"- key: {request.project_key}\n"
                f"- name: {request.project_name}\n"
                f"- repository: {request.repository_url}\n"
                f"- default branch: {request.default_branch}"
            )
            if claim.context.upstream_artifacts:
                artifacts = [
                    {
                        "producer_node_key": artifact.producer_node_key,
                        "visit_count": artifact.visit_count,
                        "outcome": artifact.outcome.value,
                        "content": artifact.content,
                    }
                    for artifact in claim.context.upstream_artifacts
                ]
                sections.append(
                    "Direct upstream artifacts:\n"
                    + json.dumps(artifacts, ensure_ascii=False, sort_keys=True, indent=2)
                )
        if claim.skill_paths:
            skills = "\n".join(
                f"- {key}: {path}" for key, path in sorted(claim.skill_paths.items())
            )
            sections.append(f"Verified skill entrypoints:\n{skills}")
        return "\n\n".join(sections)

    @staticmethod
    def _optional_string(configuration: dict[str, Any], key: str) -> str | None:
        value = configuration.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _failure_reason(terminal: dict[str, Any]) -> str:
        error = terminal.get("error")
        return error if isinstance(error, str) and error else "OpenClaw run failed"

    def _stored_result(self, execution: ExternalExecution) -> TaskResult:
        terminal = execution.terminal_result or {}
        return self._result(
            execution,
            terminal,
            succeeded=execution.status is ExternalExecutionStatus.SUCCEEDED,
        )

    @staticmethod
    def _result(
        execution: ExternalExecution, terminal: dict[str, Any], *, succeeded: bool
    ) -> TaskResult:
        usage_data = terminal.get("usage")
        usage = None
        if isinstance(usage_data, dict):
            input_tokens = usage_data.get("inputTokens", usage_data.get("input_tokens"))
            output_tokens = usage_data.get("outputTokens", usage_data.get("output_tokens"))
            if (
                isinstance(input_tokens, int)
                and not isinstance(input_tokens, bool)
                and input_tokens >= 0
                and isinstance(output_tokens, int)
                and not isinstance(output_tokens, bool)
                and output_tokens >= 0
            ):
                usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        return TaskResult(
            outcome=NodeOutcome.SUCCESS if succeeded else NodeOutcome.FAILURE,
            output={
                "provider": "openclaw",
                "session_key": execution.external_session_key,
                "run_id": execution.external_run_id,
                "terminal": terminal,
            },
            usage=usage,
        )
