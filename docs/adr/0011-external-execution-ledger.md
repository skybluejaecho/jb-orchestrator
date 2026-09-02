# ADR 0011: Persist external execution identity in PostgreSQL

- Status: Accepted
- Date: 2026-09-02

## Context

An OpenClaw run can outlive the Python coroutine and worker process that started it. Retrying a
leased workflow task without knowing the prior provider run could duplicate side effects, while
cancelling a whole session could stop unrelated work. OpenClaw owns its conversation transcript,
but JB still needs an authoritative record of why and how that runtime was invoked.

## Decision

Store one `external_executions` row per stable JB task idempotency key. The row records the JB run,
workflow execution and node, executor key, external agent/session/run identifiers, lifecycle state,
and terminal projection. PostgreSQL owns this mapping and OpenClaw continues to own conversation
history and live agent execution.

The optional `jb-openclaw-executor` package uses the official Node Gateway client through a bounded
JSON stdin/stdout bridge. Prompts and credentials are not command-line arguments. Before starting a
run, the adapter creates a `starting` record. It persists the returned run ID as `active` before
waiting. A retry resumes an active run, repeats a start only with the original idempotency key, or
returns the stored terminal result.

Cancellation resolves the mapping by the JB idempotency key and sends `sessions.abort` for the exact
external run ID. Terminal/cancellation races are treated idempotently.

## Consequences

- Worker crashes do not erase the external run identity.
- Technical retries do not blindly create new provider work.
- OpenClaw sessions can retain context without becoming the workflow database.
- The adapter remains separately installable through the executor entry-point mechanism.
- The first implementation requires Node.js and an installed pinned Gateway client bridge.
- Headless device pairing, reconnect reconciliation, and live payload verification remain required
  before a non-loopback production deployment.
