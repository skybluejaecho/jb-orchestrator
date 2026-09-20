"""Executor-specific workflow compatibility checks used before dispatch."""

from dataclasses import dataclass

from jb_orchestrator.workflows import WorkflowDefinition


@dataclass(frozen=True, slots=True)
class WorkflowCompatibilityIssue:
    """One deterministic reason a workflow cannot run on its selected executor."""

    code: str
    node_key: str
    executor_key: str
    message: str


@dataclass(frozen=True, slots=True)
class WorkflowCompatibility:
    """Compatibility assessment exposed to dispatch clients."""

    issues: tuple[WorkflowCompatibilityIssue, ...] = ()

    @property
    def compatible(self) -> bool:
        return not self.issues


def assess_workflow_compatibility(
    definition: WorkflowDefinition,
) -> WorkflowCompatibility:
    """Validate runtime contracts that are narrower than the workflow schema."""

    issues: list[WorkflowCompatibilityIssue] = []
    for node in definition.nodes:
        executor_key = node.executor_key or "default"
        if executor_key != "openclaw":
            continue
        mode = node.configuration.get("workspace_mode", "shared")
        if not isinstance(mode, str) or mode.strip() != "shared":
            issues.append(
                WorkflowCompatibilityIssue(
                    code="openclaw.workspace_mode_unsupported",
                    node_key=node.key,
                    executor_key=executor_key,
                    message=(
                        "OpenClaw supports only the preconfigured agent workspace; "
                        "git_worktree and custom workspace modes are unavailable"
                    ),
                )
            )
        cwd = node.configuration.get("cwd")
        if cwd is not None and (not isinstance(cwd, str) or bool(cwd.strip())):
            issues.append(
                WorkflowCompatibilityIssue(
                    code="openclaw.dynamic_cwd_unsupported",
                    node_key=node.key,
                    executor_key=executor_key,
                    message=(
                        "OpenClaw does not allow node-level cwd overrides; configure the "
                        "project workspace on the selected OpenClaw agent"
                    ),
                )
            )
    return WorkflowCompatibility(issues=tuple(issues))


def incompatible_workflow_message(compatibility: WorkflowCompatibility) -> str:
    """Return a stable operator-facing summary for a rejected dispatch."""

    details = "; ".join(
        f"{issue.code} at node {issue.node_key}: {issue.message}" for issue in compatibility.issues
    )
    return f"workflow is incompatible with current executor capabilities: {details}"
