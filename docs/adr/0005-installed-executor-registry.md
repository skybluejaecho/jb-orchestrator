# ADR 0005: Discover executor adapters through Python entry points

- Status: Accepted
- Date: 2026-09-01

## Context

Workflow tasks may run through Codex, Orca, OpenClaw, a local process, or future runtimes. The
orchestration core must route tasks deterministically without importing every optional SDK or
claiming work that a worker cannot execute.

## Decision

Each task node stores an `executor_key`, instructions, and JSON configuration in its immutable
workflow snapshot. Node execution rows denormalize the key so PostgreSQL can select only work
supported by a worker while holding a short row lock.

Executor packages publish no-argument factories under the `jb_orchestrator.executors` Python
entry-point group. The worker discovers those factories at startup, fails on invalid or duplicate
registrations, and advertises the resulting key set when claiming work.

## Consequences

- Adding an executor does not require changing the workflow engine.
- Workers never consume retries for task types they do not support.
- Adapter dependencies stay outside the orchestration core package.
- Executor keys are public compatibility identifiers and must be changed through versioned
  workflow definitions.
- Skills remain separate reusable context packages and will be referenced independently.
