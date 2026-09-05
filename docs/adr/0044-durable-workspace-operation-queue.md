# ADR 0044: Route workspace maintenance through a durable scope-bound queue

- Status: Accepted
- Date: 2026-09-04

## Context

ORCH-046 provides safe local inspection and cleanup commands, but a Jarvis or OpenClaw control
client may not run on the machine that owns the worktree. Letting the API process touch local Git
would couple the control plane to one filesystem and would fail when the API, worker, and repository
are deployed separately.

## Decision

Persist inspect and cleanup requests as `workspace_operations`. The Control Plane validates the
external execution, requires an idempotency key, and records the requesting service account. Cleanup
also requires the exact external execution UUID and a terminal external execution before it can be
queued.

Each managed assignment stores an opaque workspace scope derived from its resolved worktree root and
repository allowlist. `jb-openclaw workspace worker` claims only operations with the scope produced by
its own configuration. Claims use database row locks, leases, and worker-specific tokens. Expired
claims can be recovered, while completion by a worker without the current token is rejected.

The OpenClaw workspace worker performs the same filesystem checks as the local ORCH-046 commands. It
records structured inspection results or a bounded failure reason. Successful cleanup removes the
exact clean and already-merged worktree, records the external execution release, and then completes
the operation. Project SSE includes operation lifecycle events from the PostgreSQL ledger.

Introduce `workspace.manage` as a separate permission for submitting commands. Reading operation
state remains covered by `project.read` and project scope.

## Consequences

- Jarvis and remote control agents can request work without receiving filesystem access.
- Workers configured for another root or allowlist cannot claim the command.
- A cleanup crash after Git removal is retry-safe because ORCH-046 can finish from durable metadata.
- Existing assignments created before migration `0019_workspace_operations` have no scope and remain
  manageable through the direct CLI; new queued operations require an assignment created afterward.
- The queue does not fetch, commit, push, merge, or create pull requests.
