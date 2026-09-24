# ADR 0085: Use preconfigured agent workspaces for the v0.1 OpenClaw adapter

- Status: Accepted
- Date: 2026-09-20

## Context

ADR 0042 assumed that an external OpenClaw Gateway client could pass a per-run `cwd` after JB had
allocated a deterministic Git worktree. OCI acceptance against the pinned OpenClaw `v2026.8.1`
runtime disproved that assumption. Gateway preflight accepts request-level `cwd` only when the
caller belongs to the internal plugin-owned subagent runtime. The JB bridge is an external client,
so its start request is rejected before a provider run ID exists.

That rejection also exposed a separate ledger defect: an external execution prepared before
`agent.start` could remain `starting` when the provider rejected the request.

## Decision

For v0.1, an OpenClaw task uses only the workspace preconfigured on its selected OpenClaw agent.
Workflow configuration may select `agent_id`, `session_key`, and `thinking`, but may not provide
`cwd` or a custom workspace mode. In particular, `workspace_mode: git_worktree` is unsupported.

The Control Plane assesses executor compatibility when listing workflow options and immediately
before dispatch. Incompatible workflows expose stable issue codes and cannot create a request, run,
or workflow execution. Jarvis explains those issues and disables submission. The executor also
omits `cwd` from every Gateway request and closes a prepared external execution as failed when start
is rejected before a run ID is accepted.

Existing inspect and cleanup paths remain for pre-release managed-worktree records, but v0.1 does
not allocate new OpenClaw worktrees. A future dynamic-workspace implementation must integrate with
OpenClaw's plugin-owned subagent runtime or another executor contract that explicitly owns workspace
allocation.

## Consequences

- Each mutating project needs an OpenClaw agent with the correct workspace configured and mounted.
- Parallel mutating nodes must not share one checkout; operators must use separately configured
  agents/checkouts or avoid that topology.
- Unsupported workflows fail before filesystem allocation and before durable execution creation.
- PostgreSQL remains the workflow and external-run source of truth; OpenClaw continues to own agent
  session context.
- ADR 0042 remains architectural history but is not an executable v0.1 Gateway contract.
