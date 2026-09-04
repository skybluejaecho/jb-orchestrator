# ADR 0038: Resolve workflow composition for pre-dispatch previews

- Status: Accepted
- Date: 2026-09-04

## Context

Request-scoped Workflow selection lets a user or Control Agent choose an exact definition, but a
key and version alone do not explain what will run. Users need to see the stages, reusable Phase
Packs, and effective Skills before dispatch without creating a second source of orchestration truth.

## Decision

Extend the project-scoped Workflow options query with a read-only composition preview. For every
selectable latest Workflow definition, the Control Plane returns:

- the exact entry node, nodes, and edges;
- referenced Phase Packs with their names, descriptions, and Skill references; and
- the deduplicated set of direct and Phase Pack-provided Skills with source kinds.

The currently bound exact definition is also returned as `default_workflow`, even when a newer
version of the same Workflow is the latest selectable entry.

The application service resolves every exact reference through the catalog in the same unit of
work. A missing referenced component fails closed as a catalog consistency conflict. The preview
does not materialize Skill files, select a model, mutate a binding, or start an execution.

Jarvis renders this information below the request composer for the currently selected Workflow.
The MCP adapter exposes the same response so OpenClaw or another Control Agent can explain the
composition before dispatch. Actual execution continues to resolve an immutable snapshot through
the existing Workflow start path; the preview is informative rather than authoritative state.

## Consequences

- A user can inspect how planning, implementation, verification, and custom phases are assembled.
- Third-party and local Skills are visible by name and source kind before execution.
- REST, MCP, and Jarvis share one composition representation.
- Catalog inconsistencies are reported before the user relies on a misleading preview.
- Older clients remain compatible because the existing option identity fields are unchanged.
