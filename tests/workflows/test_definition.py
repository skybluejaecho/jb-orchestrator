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
