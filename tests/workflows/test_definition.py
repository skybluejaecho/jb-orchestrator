from uuid import uuid4

import pytest

from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowDefinitionError,
    WorkflowSnapshot,
    WorkflowStatus,
)


def test_definition_rejects_duplicate_node_keys() -> None:
    with pytest.raises(WorkflowDefinitionError, match="unique"):
        WorkflowDefinition(
            key="duplicate",
            version=1,
            entry_node="task",
            nodes=(
                NodeDefinition(key="task", kind=NodeKind.TASK),
                NodeDefinition(key="task", kind=NodeKind.TASK),
            ),
            edges=(),
        )


def test_definition_rejects_unreachable_node() -> None:
    with pytest.raises(WorkflowDefinitionError, match="reachable"):
        WorkflowDefinition(
            key="unreachable",
            version=1,
            entry_node="task",
            nodes=(
                NodeDefinition(key="task", kind=NodeKind.TASK),
                NodeDefinition(
                    key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
                ),
                NodeDefinition(
                    key="orphan", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.FAILED
                ),
            ),
            edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
        )


def test_snapshot_preserves_definition_version_and_run() -> None:
    definition = WorkflowDefinition(
        key="simple",
        version=3,
        entry_node="task",
        nodes=(
            NodeDefinition(key="task", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    run_id = uuid4()

    snapshot = WorkflowSnapshot.from_definition(definition, run_id=run_id)

    assert snapshot.run_id == run_id
    assert snapshot.definition_id == definition.id
    assert snapshot.definition_key == "simple"
    assert snapshot.definition_version == 3
    assert snapshot.nodes == definition.nodes


def test_only_task_nodes_accept_executor_configuration() -> None:
    with pytest.raises(WorkflowDefinitionError, match="only task"):
        NodeDefinition(
            key="approval",
            kind=NodeKind.APPROVAL,
            executor_key="codex",
        )

    with pytest.raises(WorkflowDefinitionError, match="instructions"):
        NodeDefinition(key="task", kind=NodeKind.TASK, instructions="  ")


def test_snapshot_copies_mutable_executor_configuration() -> None:
    configuration = {"model": "initial"}
    definition = WorkflowDefinition(
        key="configured",
        version=1,
        entry_node="task",
        nodes=(
            NodeDefinition(
                key="task",
                kind=NodeKind.TASK,
                executor_key="codex",
                configuration=configuration,
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    snapshot = WorkflowSnapshot.from_definition(definition, run_id=uuid4())

    configuration["model"] = "changed"

    assert snapshot.node("task").configuration == {"model": "initial"}
