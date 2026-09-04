# ADR 0042: Isolate mutating OpenClaw tasks with deterministic Git worktrees

- Status: Accepted
- Date: 2026-09-04

## Context

The Workflow engine can claim parallel task nodes, but passing the same repository `cwd` to multiple
external agents allows concurrent writes to collide. Forcing every task through one shared checkout
would avoid corruption only by removing useful parallelism. Automatically merging agent branches is
a separate policy decision with destructive and remote side effects.

## Decision

Keep the existing shared-directory behavior as the default and add the explicit node configuration
`workspace_mode: git_worktree`. An isolated node must also provide the exact repository-root `cwd`
and `workspace_base_ref`. The worker host must configure a dedicated
`JB_OPENCLAW_WORKSPACE_ROOT` and one or more `JB_OPENCLAW_REPOSITORY_ROOTS`.

The OpenClaw adapter resolves the Git top level, enforces the source allowlist, rejects overlapping
repository/worktree roots, and invokes Git with argument arrays rather than a shell. It derives one
branch and worktree path from the Workflow execution ID, node key, and visit count. A retry validates
and reuses the existing assignment. The configured base ref is resolved to an exact commit before
creation. Different parallel nodes or loop visits receive distinct paths.
Execution and node identifiers are bounded in generated paths to remain practical on Windows hosts;
the complete execution identity remains in PostgreSQL.

Workspace path, branch, and base ref are written to the external execution ledger before the provider
run starts and exposed through the existing observation API and Jarvis. Completed worktrees are kept.
The adapter does not commit, push, merge, remove, or prune Git state automatically.

## Consequences

- Parallel implementation and verification agents no longer need to share a mutable checkout.
- The explicit base ref can follow a Git Flow branch such as `develop` without hard-coding Git Flow
  into the orchestration engine.
- A worker restart can recover the same starting mapping and deterministic worktree.
- Operators must provision storage and remove reviewed worktrees deliberately.
- Remote OpenClaw Gateways can use this mode only when the generated path is visible on the Gateway
  host; otherwise workspace allocation belongs in a remote executor adapter.
