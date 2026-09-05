# ADR 0048: Execute SCM publication with a lease-bounded scoped worker

- Status: Accepted
- Date: 2026-09-05

## Context

ORCH-050 stores durable publication requests but does not execute them. A worker must bridge those
records to the installed ORCH-049 publisher adapters without allowing the wrong host or provider to
process a branch. It must also avoid recording an unrelated or malformed provider response as a
successful publication.

An SCM adapter that pushes a local branch needs the worktree path. That path already belongs to the
ExternalExecution and should not be copied into the publication ledger, where it could become stale.

## Decision

Add a dedicated SCM publication worker process. One process serves one opaque workspace scope and
all explicitly installed publisher provider keys. It checks providers in deterministic key order
and claims only records matching both its scope and one installed provider.

After a claim, the runtime reloads the ExternalExecution and rejects a released workspace, changed
scope or branch, or missing worktree path. It then builds a credential-free ScmPublicationRequest
with the current trusted worktree path and invokes the selected ScmPublisher.

Provider execution has a configurable timeout that must be shorter than the claim lease. This
ensures a timed-out call is failed while the worker still owns its lease rather than allowing two
workers to record competing outcomes. Cancellation leaves the lease to expire and be reclaimed.

Before recording success, the worker requires the provider result to repeat the exact provider,
repository, source branch, and target branch from the claimed record. Provider exceptions, timeout,
state drift, and result mismatches are recorded as durable failures.

The process is exposed as jb-scm-worker. Publisher discovery uses only the
jb_orchestrator.scm_publishers entry-point group; provider credentials remain inside those installed
adapters.

## Consequences

- API and Jarvis processes never execute Git or provider requests.
- Work is processed only on a host with the matching worktree scope and installed provider.
- A successful record cannot silently point at another repository or branch.
- The worker can be deployed independently from task and workspace-operation workers.
- A concrete publisher adapter is still required before remote publication can occur.
- Automatic merge, remote branch deletion, and local worktree cleanup remain outside this runtime.
