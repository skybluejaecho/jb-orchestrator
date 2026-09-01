# ADR 0003: Use a deterministic persisted workflow state machine

- Status: Accepted
- Date: 2026-09-01

## Context

Agent processes are non-deterministic and may stop at any time. Workflow routing, approval,
retry, and loop limits must remain reproducible independently of an agent session.

## Decision

Keep graph validation and state transitions in a deterministic domain engine. Snapshot each
workflow definition when a Run starts. Persist workflow and node execution state in PostgreSQL.
Workers will only execute READY task nodes and report outcomes back to this engine.

Task retries and graph visits are separate limits: attempts handle technical execution failures,
while visits bound intentional graph loops such as verification returning to implementation.

## Consequences

- Agent adapters cannot choose arbitrary next nodes.
- Definition changes do not alter an already-running workflow.
- Approval pauses and repair loops survive process restarts.
- ORCH-005 can add distributed workers without moving routing logic into the worker.

