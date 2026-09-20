# Spike 001: OpenClaw Gateway executor boundary

- Status: Contract implemented; live Gateway validation pending
- Date: 2026-09-02
- OpenClaw client/protocol package: `2026.8.1`
- Wire protocol: v4

## Question

Can `jb-orchestrator` use OpenClaw as an external agent runtime without making OpenClaw the source
of truth for workflow state?

## Findings

Yes. The official WebSocket Gateway protocol provides the required lifecycle primitives:

- `agent` starts a turn and immediately returns an external `runId`.
- `agent.wait` waits for that exact run's terminal snapshot.
- `sessions.abort` cancels an exact `runId` and fits the optional executor cancellation hook added
  in ORCH-012.
- A stable `sessionKey` preserves OpenClaw-owned conversation context across separate turns.
- Every side-effecting start includes the JB task's stable idempotency key.

The Gateway owns conversation transcripts and active agent execution. PostgreSQL remains the
authority for JB projects, workflow/node state, leases, budgets, approvals, selected skills,
decisions, and the mapping to external identifiers.

## Proposed production boundary

```text
PostgreSQL task lease
  -> OpenClaw executor adapter
     -> resolve/create external session mapping
     -> agent(idempotencyKey=JB task key, sessionKey=mapped key)
     -> persist external runId before waiting
     -> agent.wait(runId)
     -> normalize output and usage into TaskResult

worker timeout / lease loss / shutdown / user cancel
  -> CancellableTaskExecutor.cancel
     -> sessions.abort(runId)
```

The production mapping should include at least the JB task ID, task idempotency key, OpenClaw
Gateway/agent identity, canonical session key, external run ID, lifecycle status, last observed
event sequence, and timestamps. Secrets and device private keys are not stored in workflow tables.

## Risks to validate against a live Gateway

1. Device pairing and durable device-token rotation for a headless backend client.
2. Exact terminal payload and provider usage fields returned by the configured agent runtime.
3. Reconnect recovery using `sessions.describe`/history and known run IDs.
4. Cancellation races where a run reaches terminal state while `sessions.abort` is in flight.
5. Gateway/client release compatibility when upgrading from the pinned version.

## Decision for the next increment

Keep the Node spike isolated. After live validation, implement an OpenClaw executor adapter behind
the existing Python `TaskExecutor` and `CancellableTaskExecutor` ports. Do not expose the Gateway
protocol directly from the JB API and do not make OpenClaw session storage replace PostgreSQL.
