# ADR 0045: Keep Jarvis workspace controls ledger-backed and explicitly guarded

- Status: Accepted
- Date: 2026-09-05

## Context

ORCH-047 makes workspace inspection and cleanup remotely requestable, but operators still need a
local GUI that explains readiness and failure without granting browser code filesystem or Control
Plane credentials. Cleanup deletes a worktree and local branch, so a single unconfirmed button is
not an acceptable interface.

## Decision

Render workspace controls inside each managed external execution in Jarvis. The selected project's
default branch is the initial merge target ref and remains editable. Inspection is available while
the workspace exists. Cleanup becomes available only after the external execution is terminal and
requires the operator to enter the complete external execution UUID exactly.

The browser calls a same-origin Jarvis route. That route validates the command shape and repeats the
cleanup confirmation check before using the server-side `workspace.manage` service-account token.
Every command carries a newly generated idempotency key. Jarvis displays the durable pending,
claimed, succeeded, or failed records returned by the Control Plane; it never predicts completion.
Project SSE revisions trigger fresh operation and execution queries.

Assignments without an ORCH-047 workspace scope are identified as legacy and retain the direct CLI
workflow. Jarvis never imports the OpenClaw adapter or accesses Git paths itself.

## Consequences

- The GUI and OpenClaw CLI agree because both use the PostgreSQL operation ledger.
- Browser clients never receive the Control Plane bearer token or filesystem authority.
- Cleanup still depends on a compatible workspace worker being online.
- Existing Jarvis service accounts need the new `workspace.manage` permission before controls work.
- SCM publication, merge, and PR creation remain separate concerns.
