"""Stable JSON representations for workflow definitions and snapshots."""

from datetime import datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.workflows.models import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowSnapshot,
    WorkflowStatus,
)


def node_to_dict(node: NodeDefinition) -> dict[str, Any]:
    return {
        "key": node.key,
        "kind": node.kind.value,
        "max_attempts": node.max_attempts,
        "max_visits": node.max_visits,
        "timeout_seconds": node.timeout_seconds,
        "terminal_status": node.terminal_status.value if node.terminal_status else None,
    }


def node_from_dict(data: dict[str, Any]) -> NodeDefinition:
    terminal = data.get("terminal_status")
    return NodeDefinition(
        key=str(data["key"]),
        kind=NodeKind(str(data["kind"])),
        max_attempts=int(data["max_attempts"]),
        max_visits=int(data["max_visits"]),
        timeout_seconds=int(data["timeout_seconds"]),
        terminal_status=WorkflowStatus(str(terminal)) if terminal else None,
    )


def edge_to_dict(edge: EdgeDefinition) -> dict[str, str]:
    return {"source": edge.source, "outcome": edge.outcome.value, "target": edge.target}


def edge_from_dict(data: dict[str, Any]) -> EdgeDefinition:
    return EdgeDefinition(
        source=str(data["source"]),
        outcome=NodeOutcome(str(data["outcome"])),
        target=str(data["target"]),
    )


def definition_to_dict(definition: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": str(definition.id),
        "key": definition.key,
        "version": definition.version,
        "entry_node": definition.entry_node,
        "nodes": [node_to_dict(node) for node in definition.nodes],
        "edges": [edge_to_dict(edge) for edge in definition.edges],
    }


def definition_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=UUID(str(data["id"])),
        key=str(data["key"]),
        version=int(data["version"]),
        entry_node=str(data["entry_node"]),
        nodes=tuple(node_from_dict(node) for node in data["nodes"]),
        edges=tuple(edge_from_dict(edge) for edge in data["edges"]),
    )


def snapshot_to_dict(snapshot: WorkflowSnapshot) -> dict[str, Any]:
    return {
        "id": str(snapshot.id),
        "run_id": str(snapshot.run_id),
        "definition_id": str(snapshot.definition_id),
        "definition_key": snapshot.definition_key,
        "definition_version": snapshot.definition_version,
        "entry_node": snapshot.entry_node,
        "nodes": [node_to_dict(node) for node in snapshot.nodes],
        "edges": [edge_to_dict(edge) for edge in snapshot.edges],
        "created_at": snapshot.created_at.isoformat(),
    }


def snapshot_from_dict(data: dict[str, Any]) -> WorkflowSnapshot:
    return WorkflowSnapshot(
        id=UUID(str(data["id"])),
        run_id=UUID(str(data["run_id"])),
        definition_id=UUID(str(data["definition_id"])),
        definition_key=str(data["definition_key"]),
        definition_version=int(data["definition_version"]),
        entry_node=str(data["entry_node"]),
        nodes=tuple(node_from_dict(node) for node in data["nodes"]),
        edges=tuple(edge_from_dict(edge) for edge in data["edges"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )
