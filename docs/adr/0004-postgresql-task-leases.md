# ADR 0004: Use PostgreSQL row locks and leases for task dispatch

> 병렬 Workflow의 aggregate 잠금 범위는 ADR 0018에서 보완한다.

- Status: Accepted
- Date: 2026-09-01

## Context

Multiple local or remote workers must execute READY workflow nodes without relying on a shared
agent session. A worker can terminate after claiming work, so ownership cannot be permanent or
kept only in process memory.

## Decision

Use PostgreSQL as the initial durable task queue. Claim the oldest READY node with
`FOR UPDATE SKIP LOCKED`, transition it to RUNNING, and store a worker ID, opaque lease token,
and expiry in the same transaction. Only the matching unexpired token may renew, complete, or
fail the task. Expired leases consume a technical attempt and return to READY when retries remain.

Executors remain ports. Codex, Orca, OpenClaw, MCP, or local command adapters will implement the
same executor contract without owning workflow routing.

## Consequences

- PostgreSQL remains the source of truth for both workflow and dispatch state.
- Competing workers do not claim the same READY row.
- A crashed worker does not permanently strand a workflow.
- Delivery is at-least-once; executors receive a stable execution/node/visit idempotency key.
- A separate broker can be added later without changing engine transition rules.
