# OpenClaw Gateway spike

This isolated tool validates the external-runtime contract before it becomes a production
`jb-orchestrator` executor adapter. It uses the official Gateway client and protocol packages,
pinned to OpenClaw `2026.8.1` and wire protocol v4.

## Validated flow

```text
jb-orchestrator task idempotency key
          |
          v
agent(message, sessionKey, idempotencyKey) -> runId
          |
          +-> agent.wait(runId) -> terminal snapshot
          |
          +-> sessions.abort(runId) on timeout/shutdown/cancellation

next task for the same role/project -> agent(..., same sessionKey, new idempotencyKey)
```

`sessionKey` preserves the OpenClaw-owned conversation. `runId` identifies one active turn, and
the orchestrator's stable task idempotency key prevents duplicate side effects when a worker
retries.

## Install and test

Node.js 22.19 or newer is required.

```powershell
cd tools/openclaw-gateway-spike
npm ci
npm test
```

## Live inspection

Start or provide an OpenClaw Gateway, then set its shared bootstrap credential in the current
shell. Do not put credentials in a committed file.

```powershell
$env:OPENCLAW_GATEWAY_URL = "ws://127.0.0.1:18789"
$env:OPENCLAW_GATEWAY_TOKEN = "<gateway-token>"
npm run inspect
```

Run one turn and wait for its terminal result:

```powershell
npm run run -- --session-key "agent:reviewer:jb-orchestrator" `
  --message "Inspect the current repository state" `
  --idempotency-key "<stable-jb-task-key>"
```

Reuse the same `--session-key` with a new idempotency key to continue that conversation. `Ctrl+C`
or process termination sends `sessions.abort` for the exact active `runId` before disconnecting.

## Spike boundary

For a disposable local proof this client deliberately uses shared Gateway auth with
`deviceIdentity: null`. The production adapter must not copy this shortcut. It must provide
host-owned Ed25519 identity and device-token persistence, handle pairing, persist the mapping from
JB task/run IDs to OpenClaw `sessionKey`/`runId`, and reconcile active runs after reconnect.
