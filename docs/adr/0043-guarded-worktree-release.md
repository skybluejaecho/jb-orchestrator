# ADR 0043: Release managed worktrees only after explicit local merge proof

- Status: Accepted
- Date: 2026-09-04

## Context

ORCH-045 retains isolated branches and worktrees so operators can review their changes. Retaining
everything forever consumes disk space, but automatic cleanup could destroy uncommitted work or the
only reference to an unmerged commit. Automatically fetching, pushing, opening a PR, or merging would
also expand the worker's remote authority beyond task execution.

## Decision

Provide explicit `jb-openclaw workspace inspect` and `workspace cleanup` operator commands. Both load
the durable external execution assignment and validate its paths against the worker's configured
repository and workspace roots.

Inspection reads local Git state and reports whether the worktree is clean and its HEAD is an ancestor
of a specified local target ref. Cleanup additionally requires:

- a terminal external execution;
- an exact external execution UUID repeated through `--confirm`;
- no tracked or untracked worktree changes; and
- proof that the worktree HEAD is already contained in the selected local target ref.

After those gates, cleanup removes the exact linked worktree and deletes the exact branch reference
only if it still points to the reviewed HEAD. It records `workspace_released_at` and an append-only
event. A retry returns the durable released state; a retry after filesystem success but before the DB
commit can finish branch cleanup from the stored source repository path.

The command treats the selected ref as local evidence. It does not fetch, push, create a PR, or merge.
Operators must update and review that ref through their normal Git Flow process first.

## Consequences

- Dirty or unmerged work is retained rather than removed.
- Cleanup has a narrow local mutation boundary and explicit human authorization.
- Jarvis can distinguish retained and released workspaces from the same PostgreSQL-backed ledger.
- Remote publication and merge policies remain outside the worker and can be integrated later through
  a separately authorized SCM adapter.
