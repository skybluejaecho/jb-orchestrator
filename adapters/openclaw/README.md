# JB OpenClaw executor

Optional executor package connecting `jb-orchestrator` workers to an OpenClaw Gateway through the
official Node.js client.

## Development installation

```powershell
cd tools/openclaw-gateway-spike
npm ci
cd ../..
uv pip install --no-deps -e adapters/openclaw
uv run jb-worker --list-executors
```

The executor key is `openclaw`. Installing this package registers its entry point; the core package
does not claim OpenClaw tasks by default.

Set `JB_OPENCLAW_BRIDGE_PATH` if the bridge is not at the repository-relative default. Gateway
shared Gateway credentials are inherited by the Node subprocess through `OPENCLAW_GATEWAY_TOKEN` or
`OPENCLAW_GATEWAY_PASSWORD` and are never passed in command arguments or stored in workflow rows.

The first connection creates an Ed25519 identity below `JB_OPENCLAW_DEVICE_STATE_DIR`. Approve the
reported request with `openclaw devices approve <requestId>`, then connect once more with the
shared Gateway credential. `OPENCLAW_GATEWAY_TOKEN` is sent as protocol `auth.token`; it is not the
short-lived setup-code field `auth.bootstrapToken`. The issued operator device token is persisted
and used by later bridge processes without the shared credential. Protect this directory with
OS-account-only permissions. For remote `wss://` Gateways, set
`OPENCLAW_GATEWAY_TLS_FINGERPRINT`.

## Node configuration

An OpenClaw workflow task may set these values in its node `configuration`:

- `agent_id`: target OpenClaw agent
- `session_key`: explicit durable session key; otherwise a deterministic execution/node key is used
- `thinking`: OpenClaw thinking level

### v0.1 workspace contract

OpenClaw Gateway `v2026.8.1` accepts a request-level `cwd` only from its internal plugin-owned
subagent runtime. The JB adapter is an external Gateway client, so v0.1 never sends `cwd` and does
not create a `git_worktree` for a task. Configure the repository workspace on the OpenClaw agent,
verify it with `openclaw agents list --json`, and select that agent with `agent_id`:

```yaml
configuration:
  agent_id: example-project-worker
  thinking: low
```

The agent must already exist and its configured workspace must be visible inside the OpenClaw
Gateway deployment. Use a distinct project agent or another externally isolated checkout for
mutating work. Do not run parallel mutating nodes against one shared checkout.

Workflow option responses expose `compatible` and `compatibility_issues`. Dispatch rejects an
OpenClaw node that specifies `cwd`, `workspace_mode: git_worktree`, or another custom workspace mode
before it creates a request or run. Jarvis renders the same reasons and disables submission.
Dynamic per-run worktrees require a future plugin-owned OpenClaw subagent adapter and are outside
the v0.1 support boundary.

### Legacy managed-worktree cleanup

The inspect, cleanup, and durable workspace-operation commands remain available only for managed
workspace records created by pre-release builds. They do not allocate new v0.1 worktrees. Configure
the original workspace and repository roots before operating on such a record, then inspect it
against a local target ref:

```powershell
uv run jb-openclaw workspace inspect `
  --external-execution-id <external-execution-uuid> `
  --merged-into develop
```

Cleanup requires a terminal provider execution, a clean worktree, and a HEAD already contained in
the specified local target ref. It also requires repeating the exact external execution UUID:

```powershell
uv run jb-openclaw workspace cleanup `
  --external-execution-id <external-execution-uuid> `
  --merged-into develop `
  --confirm <external-execution-uuid>
```

The command removes only that linked worktree and deletes its exact local branch with an expected-HEAD
guard. It then records `workspace_released_at` in PostgreSQL. It never fetches, pushes, creates a PR,
or merges. Ensure the local target ref is current before using it as merge evidence, and never point
the worktree root at a repository or broad user directory.

### Durable workspace commands

Remote clients submit inspect and cleanup requests to the Control Plane instead of touching the
worker filesystem. Grant the submitting service account `project.read` and `workspace.manage` for the
project. Every POST requires an `Idempotency-Key` header. A cleanup payload must repeat the exact
external execution UUID in `confirmation`.

Run a workspace command worker only when legacy records need remote inspection or cleanup, using the
same `JB_OPENCLAW_WORKSPACE_ROOT` and `JB_OPENCLAW_REPOSITORY_ROOTS` that created them:

```powershell
uv run jb-openclaw workspace worker --worker-id local-workspaces
```

Use `--once` for one polling attempt. The worker claims only commands matching the opaque scope
derived from its configured worktree root and repository allowlist. PostgreSQL leases make a crashed
claim recoverable. Inspection and cleanup results are available from:

```text
POST /v1/external-executions/{id}/workspace-operations
GET  /v1/external-executions/{id}/workspace-operations
```

Assignments created before migration `0019_workspace_operations` have no scope and continue to use
the direct `workspace inspect` and `workspace cleanup` commands. The queue never fetches, commits,
pushes, merges, or opens a pull request.

The selected JB model profile supplies the OpenClaw provider and model override. Verified skill
entrypoint paths are appended to the task message so the agent receives the exact materialized
versions selected by the workflow snapshot.

When a phase defines an output contract, the adapter asks the agent for one JSON object without a
Markdown fence. An object returned in `agent.wait.output`, or a string containing a JSON object, is
stored as the task artifact and validated against that contract. The complete provider terminal
result remains in the external execution ledger. Non-JSON output retains a diagnostic provider
envelope and will follow the workflow failure edge when it violates a phase contract.

## Recovery behavior

- a provider rejection before a run ID is accepted closes the external execution as `failed`.
- a recovered `starting` record without a run ID repeats `agent` with the same idempotency key.
- `active` resumes `agent.wait` without starting another run.
- terminal records return their persisted normalized result without contacting OpenClaw.
- worker timeout, lease loss, or shutdown calls `sessions.abort` for the recorded exact run ID.

Before a non-loopback production deployment, validate pairing, TLS pinning, reconnect event
reconciliation, filesystem ACLs, and credential rotation against the deployed Gateway version.

## Explicit live acceptance

Live checks are deliberately excluded from CI because they require a separately operated Gateway,
credentials, and provider usage. CI instead runs the pinned official protocol contract tests in
`tools/openclaw-gateway-spike`.

After installing this adapter and the Node dependencies, diagnose the configured endpoint without
starting an agent turn:

```powershell
uv run jb-openclaw doctor
```

Then use a dedicated session and a new stable prefix for one explicit acceptance attempt. This
starts two agent turns: the first request is replayed with the same idempotency key, and the second
request proves continuation on the same session.

```powershell
uv run jb-openclaw acceptance `
  --session-key "agent:<configured-agent-id>:jb-orchestrator:acceptance" `
  --idempotency-prefix "acceptance-2026-09-04-01" `
  --message "Return a short acknowledgement for the JB acceptance check."
```

Add `--verify-cancellation` only when the deployed Gateway's cancellation path must also be tested;
it starts one additional turn and immediately aborts its exact run ID. Reusing an idempotency prefix
reuses the corresponding Gateway run rather than creating a new attempt. The command reports only
Gateway health/count summaries and run identifiers, not prompts, session contents, or credentials.
