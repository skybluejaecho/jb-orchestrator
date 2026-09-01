from uuid import uuid4

from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowSnapshot,
    WorkflowStatus,
)
from jb_orchestrator.workflows.serialization import (
    definition_from_dict,
    definition_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)


def test_definition_and_snapshot_json_round_trip() -> None:
    definition = WorkflowDefinition(
        key="serialized",
        version=3,
        entry_node="task",
        nodes=(
            NodeDefinition(
                key="task",
                kind=NodeKind.TASK,
                max_attempts=2,
                executor_key="codex",
                instructions="Implement the approved task.",
                configuration={"reasoning_effort": "medium"},
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="task", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    snapshot = WorkflowSnapshot.from_definition(definition, run_id=uuid4())

    restored_definition = definition_from_dict(definition_to_dict(definition))
    restored_snapshot = snapshot_from_dict(snapshot_to_dict(snapshot))

    assert restored_definition == definition
    assert restored_snapshot == snapshot
