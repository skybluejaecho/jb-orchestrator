# ADR 0046: Keep SCM publication behind provider-neutral installed adapters

- Status: Accepted
- Date: 2026-09-05

## Context

ORCH-048 lets an operator inspect and release an executor-owned worktree, but publication still
requires manually pushing its branch and opening a review. GitHub calls this review a pull request
and GitLab calls it a merge request. Embedding either provider API in Jarvis, the OpenClaw executor,
or the orchestration domain would bind credentials and provider-specific behavior to the wrong
layer.

Publication is also materially different from cleanup. It mutates a remote repository and may
notify other people, while cleanup only removes already-merged local state. The two operations need
separate permissions, audit records, and workers.

## Decision

Define a provider-neutral `ScmPublisher` port with one operation: `publish_review`. Its request
contains only repository identity, source and target branches, review title and body, and an
idempotency key. It never contains credentials. The result records stable provider, repository,
branch, review URL, and review ID values.

SCM adapters are installed under the `jb_orchestrator.scm_publishers` Python entry-point group and
selected by an explicit provider key. Factories take no arguments; each adapter reads credentials
and provider configuration from its own runtime environment or secret store. Registration rejects
duplicate keys, non-conforming adapters, and synchronous publication methods.

The contract creates or reuses a remote review but does not merge it, delete branches, release
worktrees, or infer a provider from a repository string. A later durable publication command will
carry the explicit provider key through PostgreSQL and invoke this port from a separately
authorized worker.

## Consequences

- GitHub and GitLab adapters can be packaged and deployed independently.
- Jarvis and OpenClaw remain clients of the Control Plane rather than owners of SCM credentials.
- Publication retries have a provider-independent idempotency identity.
- This increment performs no remote mutation by itself; the durable command ledger, permission,
  worker runtime, and concrete providers remain subsequent increments.
- Merge automation remains outside the publication contract and requires a separate decision.
