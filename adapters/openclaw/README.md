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
bootstrap credentials are inherited by the Node subprocess through `OPENCLAW_GATEWAY_TOKEN` or
`OPENCLAW_GATEWAY_PASSWORD` and are never passed in command arguments or stored in workflow rows.

The first connection creates an Ed25519 identity below `JB_OPENCLAW_DEVICE_STATE_DIR`. Approve the
reported request with `openclaw devices approve <requestId>`, then connect once more with the
bootstrap credential. The issued operator device token is persisted and used by later bridge
processes without the shared credential. Protect this directory with OS-account-only permissions.
For remote `wss://` Gateways, set `OPENCLAW_GATEWAY_TLS_FINGERPRINT`.

## Node configuration

An OpenClaw workflow task may set these values in its node `configuration`:

- `agent_id`: target OpenClaw agent
- `session_key`: explicit durable session key; otherwise a deterministic execution/node key is used
- `cwd`: agent working directory
- `thinking`: OpenClaw thinking level
- `workspace_mode`: `shared` (default) or explicit `git_worktree` isolation
- `workspace_base_ref`: required Git ref when `workspace_mode` is `git_worktree`

### Isolated Git worktrees

Use `git_worktree` for parallel nodes that may modify the same repository. Configure a dedicated
worktree root outside every source repository and an allowlist of source-repository parent paths:

```powershell
$env:JB_OPENCLAW_WORKSPACE_ROOT = "C:\worktrees\jb-orchestrator"
$env:JB_OPENCLAW_REPOSITORY_ROOTS = '["C:\\projects"]'
```

Then configure the task node with the exact local repository root and an explicit base ref:

```yaml
configuration:
  cwd: C:/projects/example-project
  workspace_mode: git_worktree
  workspace_base_ref: develop
```

The adapter resolves the configured base ref to one commit, then creates a deterministic branch and
path for each Workflow execution, node, and visit.
Retries validate and reuse that assignment; independent parallel nodes receive different worktrees.
The source repository must be below an allowed root, `cwd` must be its exact Git top-level path, and
the worktree root must not contain or be contained by the repository. Git is invoked without a shell.

Completed worktrees and branches are intentionally retained for review, commit, push, or merge. This
increment does not automatically merge or delete them. Remove reviewed worktrees with an explicit
operator Git command and never point the worktree root at a repository or broad user directory.

The selected JB model profile supplies the OpenClaw provider and model override. Verified skill
entrypoint paths are appended to the task message so the agent receives the exact materialized
versions selected by the workflow snapshot.

When a phase defines an output contract, the adapter asks the agent for one JSON object without a
Markdown fence. An object returned in `agent.wait.output`, or a string containing a JSON object, is
stored as the task artifact and validated against that contract. The complete provider terminal
result remains in the external execution ledger. Non-JSON output retains a diagnostic provider
envelope and will follow the workflow failure edge when it violates a phase contract.

## Recovery behavior

- `starting` without a run ID repeats `agent` with the same idempotency key.
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
  --session-key "agent:acceptance:jb-orchestrator" `
  --idempotency-prefix "acceptance-2026-09-04-01" `
  --message "Return a short acknowledgement for the JB acceptance check."
```

Add `--verify-cancellation` only when the deployed Gateway's cancellation path must also be tested;
it starts one additional turn and immediately aborts its exact run ID. Reusing an idempotency prefix
reuses the corresponding Gateway run rather than creating a new attempt. The command reports only
Gateway health/count summaries and run identifiers, not prompts, session contents, or credentials.
