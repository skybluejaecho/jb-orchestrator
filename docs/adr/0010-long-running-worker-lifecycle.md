# ADR 0010: Renew leases and cancel long-running executors cooperatively

- Status: Accepted
- Date: 2026-09-02

## Context

Agent runtimes can execute longer than a single database lease interval and may continue work in
an external service after the local worker stops waiting. A worker that loses lease ownership must
not publish a late result, while shutdown and timeout handling must not leave an OpenClaw, Codex,
or other provider run consuming resources without supervision.

## Decision

The worker runs executor execution, lease heartbeat, and optional shutdown monitoring as sibling
async tasks. It renews the PostgreSQL lease at a configurable interval and treats heartbeat failure
as loss of safe ownership: the executor is cancelled and the task is failed through the normal
retry policy. Executor timeout and worker shutdown use the same cancellation path.

Local coroutine cancellation is always attempted. Adapters that own provider-side work may also
implement the optional `CancellableTaskExecutor.cancel(claim)` hook. The hook must be idempotent
and use the claim idempotency key or its mapped external run identifier. Local and provider
cancellation are bounded by a configurable timeout so shutdown cannot block forever.

Cancellation and lease failures consume a technical attempt, consistent with expired-lease
recovery. The stable node-visit idempotency key remains unchanged across technical retries.

## Consequences

- Active workers retain explicit lease ownership during long model or agent runs.
- A database outage stops unsupervised executor work instead of accepting an unsafe late result.
- OpenClaw and similar adapters have a standard hook for cancelling external sessions or runs.
- Worker shutdown waits for bounded cleanup and persists the task outcome before exiting.
- Adapter cancellation must tolerate duplicate calls and partial network failure.
