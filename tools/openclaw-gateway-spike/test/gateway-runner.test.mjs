import assert from "node:assert/strict";
import test from "node:test";

import { GatewayContractError, GatewayRunCoordinator } from "../src/gateway-runner.mjs";

class FakeRpc {
  constructor(responses = new Map()) {
    this.responses = responses;
    this.calls = [];
  }

  async request(method, params, options) {
    this.calls.push({ method, params, options });
    const response = this.responses.get(method);
    return typeof response === "function" ? response(params) : response ?? {};
  }
}

test("starts an idempotent run and waits for its terminal result", async () => {
  const rpc = new FakeRpc(
    new Map([
      ["agent", { runId: "run-123", acceptedAt: 1234 }],
      ["agent.wait", { status: "ok", output: "done" }],
    ]),
  );
  const coordinator = new GatewayRunCoordinator(rpc);

  const result = await coordinator.run({
    message: "Validate the change",
    sessionKey: "agent:reviewer:orch-013",
    idempotencyKey: "workflow-task-123",
    waitTimeoutMs: 30_000,
  });

  assert.equal(result.runId, "run-123");
  assert.deepEqual(rpc.calls, [
    {
      method: "agent",
      params: {
        message: "Validate the change",
        sessionKey: "agent:reviewer:orch-013",
        idempotencyKey: "workflow-task-123",
        deliver: false,
      },
      options: undefined,
    },
    {
      method: "agent.wait",
      params: { runId: "run-123", timeoutMs: 30_000 },
      options: { timeoutMs: 35_000 },
    },
  ]);
});

test("reuses the caller-provided session key across independent turns", async () => {
  let sequence = 0;
  const rpc = new FakeRpc(
    new Map([
      ["agent", () => ({ runId: `run-${++sequence}` })],
      ["agent.wait", { status: "ok" }],
    ]),
  );
  const coordinator = new GatewayRunCoordinator(rpc);

  await coordinator.run({
    message: "first",
    sessionKey: "agent:builder:project-a",
    idempotencyKey: "task-1",
  });
  await coordinator.run({
    message: "continue",
    sessionKey: "agent:builder:project-a",
    idempotencyKey: "task-2",
  });

  const starts = rpc.calls.filter((call) => call.method === "agent");
  assert.deepEqual(
    starts.map((call) => call.params.sessionKey),
    ["agent:builder:project-a", "agent:builder:project-a"],
  );
  assert.deepEqual(
    starts.map((call) => call.params.idempotencyKey),
    ["task-1", "task-2"],
  );
});

test("cancels only the exact external run", async () => {
  const rpc = new FakeRpc(new Map([["sessions.abort", { ok: true }]]));
  const coordinator = new GatewayRunCoordinator(rpc);

  await coordinator.cancel("run-456");

  assert.deepEqual(rpc.calls, [
    { method: "sessions.abort", params: { runId: "run-456" }, options: undefined },
  ]);
});

test("rejects invalid requests before contacting the Gateway", async () => {
  const rpc = new FakeRpc();
  const coordinator = new GatewayRunCoordinator(rpc);

  await assert.rejects(
    coordinator.start({
      message: "",
      sessionKey: "agent:reviewer:orch-013",
      idempotencyKey: "task-invalid",
    }),
    GatewayContractError,
  );
  assert.equal(rpc.calls.length, 0);
});

test("rejects an accepted response without a run id", async () => {
  const rpc = new FakeRpc(new Map([["agent", { acceptedAt: 1234 }]]));
  const coordinator = new GatewayRunCoordinator(rpc);

  await assert.rejects(
    coordinator.start({
      message: "hello",
      sessionKey: "agent:reviewer:orch-013",
      idempotencyKey: "task-no-run-id",
    }),
    /did not include a runId/,
  );
});
