# ADR 0041: Show external agent ownership from the durable ledger in Jarvis

- Status: Accepted
- Date: 2026-09-04

## Context

Jarvis shows Workflow node state and artifacts, but those projections do not answer which external
agent session owns an active turn. Operators otherwise have to correlate a node with OpenClaw or
another executor manually. Reading runtime state directly from a provider would also conflict with
the Control Plane's role as the system of record and would require provider credentials in Jarvis.

## Decision

Extend the existing server-side execution-detail proxy to request external execution records filtered
by the exact Workflow execution ID. Jarvis renders each durable record with its node key, executor
key, external agent ID, session key, run ID, normalized status, and failure reason.

The browser continues to call only the Jarvis route. Its service-account token remains server-side,
and Jarvis does not receive OpenClaw credentials. The detail response does not add the provider's
terminal result payload because task artifacts already expose the intended user-facing output and
the runtime panel exists only to explain assignment and execution ownership.

Project SSE events already include external execution transitions, so the existing detail refresh
path updates these records without adding a second browser event stream.

## Consequences

- Users can identify the external sub-agent, durable session, and exact turn from the local GUI.
- Jarvis and other clients continue to agree because they read the same PostgreSQL-backed ledger.
- Historical retries can appear as multiple external records for one node rather than being hidden.
- This change provides observability, not filesystem isolation; isolated concurrent workspaces remain
  a separate executor and repository-lifecycle concern.
