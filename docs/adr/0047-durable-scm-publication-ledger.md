# ADR 0047: Route SCM publication through a durable, scoped command ledger

- Status: Accepted
- Date: 2026-09-05

## Context

ORCH-049 defines an installable SCM publisher contract, but invoking a remote mutation directly
from Jarvis or an API request would lose the command if the process stopped and would couple the
request lifecycle to provider latency. Publication must also be routed to a host that can access
the exact managed worktree while holding provider credentials.

Allowing callers to submit repository and source branch values would let a compromised client
redirect an otherwise valid publication credential. Publication therefore needs to derive those
values from trusted orchestration records.

## Decision

Store each publication request in PostgreSQL with pending, claimed, succeeded, or failed status.
The record contains its external execution, explicit provider key, repository, source and target
branches, review text, workspace scope, requester, idempotency key, lease state, result, and failure
reason.

The Control Plane derives the repository from the registered Project and the source branch and
workspace scope from the ExternalExecution. A request is accepted only after the external execution
is terminal and while its managed workspace remains unreleased. The caller supplies only the
provider key, target branch, title, body, and idempotency header.

Workers claim commands by both provider key and opaque workspace scope. Expired leases may be
reclaimed. Completion requires the current lease token, and every lifecycle transition emits a
project-observable event.

Writing uses the independent scm.publish permission. Reading continues to use project.read.
Provider credentials are not represented in the API or database.

## Consequences

- A publication request survives API, Jarvis, and worker restarts.
- Retried client requests cannot create duplicate ledger records.
- Workers cannot claim repositories outside their configured provider and filesystem scope.
- Project SSE can refresh publication state without becoming the source of truth.
- This increment does not execute Git or provider API calls. A following worker increment will map
  a claimed record to the ORCH-049 ScmPublisher contract.
- Merge and branch deletion remain separate, explicitly authorized operations.
